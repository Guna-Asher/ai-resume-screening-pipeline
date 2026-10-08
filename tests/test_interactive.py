"""Guided CLI with scripted answers. The runner is the real run_batch (offline: no LLM, no GitHub)."""
import json

import pytest

import main as main_module
from src.cli import interactive
from src.cli.interactive import run_interactive
from src.extraction import ResumeExtractor
from src.pipeline import run_batch

from .pdf_fixtures import RESUME_LINES, make_pdf, make_zip, pdf_bytes


def offline_runner(path):
    return run_batch(path, ResumeExtractor(None))


class Script:
    """Feeds scripted answers to input(); records the prompts; fails loudly if the flow asks too much."""

    def __init__(self, monkeypatch, answers):
        self.answers, self.prompts = list(answers), []
        monkeypatch.setattr("builtins.input", self)

    def __call__(self, prompt=""):
        self.prompts.append(prompt)
        if not self.answers:
            raise AssertionError(f"unexpected extra prompt: {prompt!r}")
        a = self.answers.pop(0)
        if isinstance(a, BaseException):
            raise a
        return a


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(interactive, "_clipboard_command", lambda: None)   # never touch the real clipboard
    for var in ("OPENROUTER_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def pdf_file(tmp_path):
    p = tmp_path / "asha.pdf"
    make_pdf(p, RESUME_LINES)
    return p


@pytest.fixture
def resume_dir(tmp_path, pdf_file):
    d = tmp_path / "resumes"
    d.mkdir()
    (d / "asha.pdf").write_bytes(pdf_file.read_bytes())
    return d


@pytest.fixture
def zip_file(tmp_path):
    z = tmp_path / "batch.zip"
    make_zip(z, {"r/a.pdf": pdf_bytes(tmp_path), "r/b.pdf": pdf_bytes(tmp_path, RESUME_LINES + ["- Built a Python agent."])})
    return z


def go(monkeypatch, answers, capsys):
    script = Script(monkeypatch, answers)
    code = run_interactive(offline_runner)
    return code, capsys.readouterr().out, script


def test_single_pdf_flow(monkeypatch, capsys, pdf_file):
    code, out, s = go(monkeypatch, ["1", str(pdf_file), "1", "", "4"], capsys)
    assert code == 0 and s.answers == []
    assert "# AI Resume Screening" in out and "Interactive Screening Workflow" in out
    assert "Input type     : Single PDF" in out and "Total resumes : 1" in out and "Ranked        : 1" in out
    assert "OpenRouter     : Not configured" in out and "unauthenticated public API" in out


def test_directory_flow_with_default_path(monkeypatch, capsys, resume_dir):
    # Enter on the directory prompt accepts ./resumes (relative to cwd, which is tmp_path)
    code, out, _ = go(monkeypatch, ["2", "", "1", "", "4"], capsys)
    assert code == 0 and "Input type     : Directory of PDFs" in out and "Total resumes : 1" in out


def test_zip_flow(monkeypatch, capsys, zip_file):
    code, out, _ = go(monkeypatch, ["3", str(zip_file), "1", "y", "4"], capsys)
    assert code == 0 and "Input type     : ZIP archive" in out and "Total resumes : 2" in out
    assert "Processing resumes..." in out and "Processing Complete" in out


def test_invalid_menu_choices_reprompt(monkeypatch, capsys, pdf_file):
    code, out, s = go(monkeypatch, ["9", "abc", "", "1", str(pdf_file), "7", "x", "1", "", "5", "4"], capsys)
    assert code == 0 and s.answers == []
    assert out.count("Invalid choice") == 6


def test_invalid_paths_reprompt_with_specific_messages(monkeypatch, capsys, pdf_file, resume_dir, zip_file, tmp_path):
    (tmp_path / "notes.txt").write_text("x")
    answers = ["1", str(resume_dir), "", str(tmp_path / "missing.pdf"), str(tmp_path / "notes.txt"), str(pdf_file),
               "1", "n"]
    _, out, _ = go(monkeypatch, answers, capsys)
    assert out.count("That path is not a PDF file.") == 3 and "Please enter a path." in out

    _, out, _ = go(monkeypatch, ["2", str(pdf_file), str(resume_dir), "1", "n"], capsys)
    assert "That path is not a directory." in out
    _, out, _ = go(monkeypatch, ["3", str(pdf_file), str(zip_file), "1", "n"], capsys)
    assert "That path is not a .zip archive." in out


def test_tilde_and_quotes_in_paths_are_accepted(monkeypatch, capsys, pdf_file, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _, out, _ = go(monkeypatch, ["1", f"'~/{pdf_file.name}'", "1", "n"], capsys)
    assert f"Input          : {pdf_file}" in out


def test_answering_no_cancels_without_running_the_pipeline(monkeypatch, capsys, pdf_file):
    calls = []
    Script(monkeypatch, ["1", str(pdf_file), "1", "no"])
    code = run_interactive(lambda p: calls.append(p))
    out = capsys.readouterr().out
    assert code == 0 and calls == [] and "Processing cancelled." in out and "Processing Complete" not in out


def test_enter_accepts_the_default_yes(monkeypatch, capsys, pdf_file):
    _, out, s = go(monkeypatch, ["1", str(pdf_file), "1", "", "4"], capsys)
    assert any(p.startswith("Start Processing? [Y/n]") for p in s.prompts) and "Processing Complete" in out


def test_terminal_only_prints_json_and_writes_nothing(monkeypatch, capsys, pdf_file, tmp_path):
    _, out, _ = go(monkeypatch, ["1", str(pdf_file), "1", "", "4"], capsys)
    assert "JSON Result" in out and '"results": [' in out
    assert not (tmp_path / "output").exists()


def test_save_to_file_creates_directory_and_matches_terminal_json(monkeypatch, capsys, pdf_file, tmp_path):
    _, out, _ = go(monkeypatch, ["1", str(pdf_file), "2", "", "", "", "4"], capsys)   # default path, no TXT, default "Y"
    saved = (tmp_path / "output" / "results.json").read_text(encoding="utf-8")
    assert saved.endswith("\n") and json.loads(saved)["ranked"] == 1
    assert saved in out                                  # the printed JSON is exactly the saved JSON
    assert "Saved:\n./output/results.json" in out and "JSON file      : ./output/results.json" in out


def test_save_only_does_not_print_json_but_saves_it(monkeypatch, capsys, pdf_file, tmp_path):
    target = tmp_path / "sub" / "dir" / "r.json"
    _, out, _ = go(monkeypatch, ["1", str(pdf_file), "3", str(target), "n", "", "4"], capsys)
    assert "JSON Result" not in out and json.loads(target.read_text())["total_files"] == 1


def test_save_json_and_txt(monkeypatch, capsys, pdf_file, tmp_path):
    _, out, _ = go(monkeypatch, ["1", str(pdf_file), "2", "", "y", "", "", "4"], capsys)
    txt = (tmp_path / "output" / "results.txt").read_text(encoding="utf-8")
    assert "AI RESUME SCREENING RESULTS" in txt and "Ranked: 1" in txt
    assert (tmp_path / "output" / "results.json").exists()


def test_overwrite_is_refused_by_default_and_reprompts(monkeypatch, capsys, pdf_file, tmp_path):
    existing = tmp_path / "results.json"
    existing.write_text("ORIGINAL")
    # Enter (default N) -> asked again; 'n' -> asked again; then a new name
    _, out, s = go(monkeypatch, ["1", str(pdf_file), "2", str(existing), "", str(existing), "n", "fresh.json",
                                 "n", "", "4"], capsys)
    assert existing.read_text() == "ORIGINAL"
    assert any("results.json already exists. Overwrite? [y/N]" in p for p in s.prompts)
    assert json.loads((tmp_path / "fresh.json").read_text())["ranked"] == 1


def test_overwrite_confirmed_replaces_the_file(monkeypatch, capsys, pdf_file, tmp_path):
    existing = tmp_path / "results.json"
    existing.write_text("ORIGINAL")
    go(monkeypatch, ["1", str(pdf_file), "3", str(existing), "y", "n", "", "4"], capsys)
    assert json.loads(existing.read_text())["ranked"] == 1


def test_export_menu_saves_the_same_result_without_rerunning_the_pipeline(monkeypatch, capsys, pdf_file, tmp_path):
    runs = []

    def counting(path):
        runs.append(path)
        return offline_runner(path)
    Script(monkeypatch, ["1", str(pdf_file), "1", "", "1", "2", "a.json", "3", "b.json", "b.txt", "4"])
    assert run_interactive(counting) == 0
    out = capsys.readouterr().out
    assert len(runs) == 1
    a, b = (tmp_path / "a.json").read_text(), (tmp_path / "b.json").read_text()
    assert a == b and a in out and (tmp_path / "b.txt").read_text().startswith("AI RESUME SCREENING RESULTS")
    assert "Clipboard is unavailable. JSON remains available above." in out


def test_clipboard_used_when_available(monkeypatch, capsys, pdf_file):
    sent = {}
    monkeypatch.setattr(interactive, "_clipboard_command", lambda: ["fake-clip"])
    monkeypatch.setattr(interactive.subprocess, "run", lambda cmd, input, check, timeout: sent.update(cmd=cmd, data=input))
    _, out, _ = go(monkeypatch, ["1", str(pdf_file), "1", "", "1", "4"], capsys)
    assert sent["cmd"] == ["fake-clip"] and json.loads(sent["data"])["ranked"] == 1 and "copied to clipboard" in out


def test_unwritable_output_is_reported_not_raised(monkeypatch, capsys, pdf_file, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file")
    Script(monkeypatch, ["1", str(pdf_file), "3", str(blocker / "x.json"), str(tmp_path / "ok.json"), "n", "", "4"])
    assert run_interactive(offline_runner) == 0
    assert "is not a directory" in capsys.readouterr().out and (tmp_path / "ok.json").exists()


def test_ctrl_c_exits_cleanly_at_any_point(monkeypatch, capsys, pdf_file):
    for answers in ([KeyboardInterrupt()], ["1", KeyboardInterrupt()], ["1", str(pdf_file), "1", KeyboardInterrupt()]):
        Script(monkeypatch, answers)
        assert run_interactive(offline_runner) == 130
        out = capsys.readouterr().out
        assert "Processing cancelled." in out and "Traceback" not in out


def test_ctrl_c_during_processing(monkeypatch, capsys, pdf_file):
    def interrupted(path):
        raise KeyboardInterrupt
    Script(monkeypatch, ["1", str(pdf_file), "1", ""])
    assert run_interactive(interrupted) == 130
    assert "Processing cancelled." in capsys.readouterr().out


def test_closed_stdin_gives_a_helpful_message(monkeypatch, capsys):
    Script(monkeypatch, [EOFError()])
    assert run_interactive(offline_runner) == 2
    assert "docker run -it" in capsys.readouterr().err


def test_main_dispatch(monkeypatch, pdf_file, tmp_path):
    called = []
    monkeypatch.setattr(main_module, "run_interactive", lambda: called.append("interactive") or 0)
    assert main_module.main([]) == 0 and called == ["interactive"]
    monkeypatch.setattr(main_module, "screen_inputs", offline_runner)
    out = tmp_path / "flag.json"
    assert main_module.main(["--input", str(pdf_file), "--output", str(out)]) == 0
    assert called == ["interactive"] and json.loads(out.read_text())["ranked"] == 1   # flag mode did not prompt
