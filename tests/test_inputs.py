"""Input normalisation: dir / single PDF / ZIP / mixed all end up as the same PDF collection."""
import tempfile
from pathlib import Path

import pytest

from src.extraction import ResumeExtractor, parse_resume_text
from src.ingestion import InputLimits, collect_inputs, ingest_paths
from src.models import ScreeningStatus
from src.pipeline import run_batch

from .pdf_fixtures import RESUME_LINES, make_linked_pdf, make_pdf, make_zip, pdf_bytes


def run(sources, **kw):
    return run_batch(sources, ResumeExtractor(None), **kw)


def names(summary):
    return {r.source_file: r for r in summary.results}


def test_single_pdf(tmp_path):
    make_pdf(tmp_path / "one.pdf", RESUME_LINES)
    s = run(tmp_path / "one.pdf")
    assert (s.total_files, s.ranked) == (1, 1) and list(names(s)) == ["one.pdf"]


def test_directory_including_subfolders(tmp_path):
    (tmp_path / "team").mkdir()
    make_pdf(tmp_path / "a.pdf", RESUME_LINES)
    make_pdf(tmp_path / "team" / "b.pdf", RESUME_LINES[:-3] + ["- Built a Python agent using LangChain."])
    s = run(tmp_path)
    assert s.total_files == 2 and set(names(s)) == {"a.pdf", "team/b.pdf"}


def test_zip_with_nested_folders(tmp_path):
    data = pdf_bytes(tmp_path)
    make_zip(tmp_path / "batch.zip", {"resumes/a.pdf": data, "resumes/deep/er/b.PDF": data + b" "})
    s = run(tmp_path / "batch.zip")
    assert s.total_files == 2 and set(names(s)) == {"batch.zip/resumes/a.pdf", "batch.zip/resumes/deep/er/b.PDF"}


def test_mixed_pdf_and_zip_and_cross_source_duplicate(tmp_path):
    data = pdf_bytes(tmp_path)
    (tmp_path / "direct.pdf").write_bytes(data)
    make_zip(tmp_path / "z.zip", {"same_bytes.pdf": data, "other.pdf": pdf_bytes(tmp_path, RESUME_LINES + ["- Built X in Python."])})
    s = run([tmp_path / "direct.pdf", tmp_path / "z.zip"])
    assert s.total_files == 3 and s.duplicates_skipped == 1 and s.ranked == 2   # SHA-256, across sources


def test_unsupported_files_are_ignored_and_reported(tmp_path):
    (tmp_path / "notes.txt").write_text("hi")
    make_pdf(tmp_path / "a.pdf", RESUME_LINES)
    make_zip(tmp_path / "z.zip", {"readme.md": b"x", "run.sh": b"#!/bin/sh", "inner.zip": b"PK", "__MACOSX/._a.pdf": b"x"})
    s = run(tmp_path)
    assert s.total_files == 1 and s.ranked == 1
    assert set(s.ignored_files) == {"notes.txt", "z.zip/readme.md", "z.zip/run.sh", "z.zip/inner.zip"}


def test_malformed_zip_fails_only_itself(tmp_path):
    make_pdf(tmp_path / "a.pdf", RESUME_LINES)
    (tmp_path / "bad.zip").write_bytes(b"this is not a zip")
    s = run(tmp_path)
    got = names(s)
    assert got["a.pdf"].status is ScreeningStatus.RANKED
    assert got["bad.zip"].status is ScreeningStatus.FAILED and "corrupt ZIP" in got["bad.zip"].error
    assert s.total_files == 2


def test_zip_slip_entries_are_rejected_and_never_written(tmp_path):
    work = tmp_path / "work"; work.mkdir()
    data = pdf_bytes(tmp_path)
    make_zip(tmp_path / "evil.zip", {"../evil.pdf": data, "/abs/evil2.pdf": data, "a/../../evil3.pdf": data,
                                     "..\\evil4.pdf": data, "ok.pdf": data})
    got = collect_inputs(tmp_path / "evil.zip", work)
    assert [p.name for p in got.pdfs] == ["evil.zip/ok.pdf"]
    assert len(got.problems) == 4 and all("path traversal" in p.message for p in got.problems)
    assert not any(tmp_path.glob("evil*.pdf")) and not any(tmp_path.parent.glob("evil*.pdf"))
    assert not (work.parent / "evil.pdf").exists()


def test_limits_are_enforced(tmp_path):
    data = pdf_bytes(tmp_path)
    make_zip(tmp_path / "z.zip", {f"{i}.pdf": data + bytes([i]) for i in range(5)})
    with tempfile.TemporaryDirectory() as w:
        got = collect_inputs(tmp_path / "z.zip", Path(w), InputLimits(max_files=3))
    assert len(got.pdfs) == 3 and any("more than 3 PDFs" in p.message for p in got.problems)

    with tempfile.TemporaryDirectory() as w:
        got = collect_inputs(tmp_path / "z.zip", Path(w), InputLimits(max_file_bytes=100))
    assert got.pdfs == [] and len(got.problems) == 5

    with tempfile.TemporaryDirectory() as w:
        got = collect_inputs(tmp_path / "z.zip", Path(w), InputLimits(max_archive_bytes=10))
    assert got.pdfs == [] and "ZIP larger" in got.problems[0].message


def test_limits_from_env():
    lim = InputLimits.from_env({"MAX_FILES": "7", "MAX_PDF_MB": "1.5", "MAX_ZIP_MB": "oops"})
    assert lim.max_files == 7 and lim.max_file_bytes == int(1.5 * 1024 * 1024)
    assert lim.max_archive_bytes == InputLimits().max_archive_bytes


def test_zip_extraction_directory_is_cleaned_up(tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"; scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    make_zip(tmp_path / "z.zip", {"a.pdf": pdf_bytes(tmp_path)})
    assert run(tmp_path / "z.zip").ranked == 1
    assert list(scratch.iterdir()) == []


def test_missing_input_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        run(tmp_path / "nope")


def test_github_link_hidden_behind_link_text_is_recovered(tmp_path):
    make_linked_pdf(tmp_path / "linked.pdf", [l for l in RESUME_LINES if "github.com" not in l], "https://github.com/hidden-user")
    work = tmp_path / "work"; work.mkdir()
    doc = ingest_paths(collect_inputs(tmp_path / "linked.pdf", work).pdfs)[0]
    assert "github.com/hidden-user" in doc.text
    assert parse_resume_text("x.pdf", doc.text).github_username == "hidden-user"
