"""Guided terminal workflow: collect configuration, confirm, run the existing pipeline, present the JSON.

Presentation only. Nothing here computes eligibility, scores, penalties, ranks or GitHub points: the
BatchSummary comes from the same pipeline entry point as the flag-based CLI, and the JSON shown, copied
and saved is the exact string `summary_json()` produces (the same one the web API returns).
"""
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.models import BatchSummary
from src.pipeline import render_text, screen_inputs, summary_json

RULE = "─" * 40
DEFAULT_RESUMES_DIR = "./resumes"
DEFAULT_JSON_PATH = "./output/results.json"
DEFAULT_TEXT_PATH = "./output/results.txt"

INPUT_TYPES = ("Single PDF", "Directory of PDFs", "ZIP archive")
OUTPUT_MODES = ("Display JSON in terminal only", "Display JSON and save to file", "Save to file only")

Runner = Callable[[Path], BatchSummary]


@dataclass
class Config:
    input_type: str
    input_path: Path
    show_json: bool
    json_path: Path | None
    text_path: Path | None


# ---------------------------------------------------------------- low-level prompts

def _heading(title: str) -> None:
    print(f"\n{RULE}\n{title}\n{RULE}\n")


def _choose(title: str, options: Sequence[str], prompt: str | None = None) -> int:
    """Numbered menu; reprompts until valid. Returns the 1-based choice."""
    print(f"\n{title}\n")
    for i, opt in enumerate(options, 1):
        print(f"{i}. {opt}")
    prompt = prompt or f"Enter choice [1-{len(options)}]"
    while True:
        answer = input(f"\n{prompt}: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer)
        print(f"Invalid choice. Please enter a number from 1 to {len(options)}.")


def _yes_no(prompt: str, default: bool) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    while True:
        answer = input(f"{prompt} {hint}: ").strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer y or n.")


def _clean_path(raw: str) -> Path:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":   # drag-and-drop into a terminal adds quotes
        raw = raw[1:-1]
    return Path(os.path.expanduser(raw))


def _shown(path: Path) -> str:
    """Display form: relative paths keep a leading ./ (Path() would drop it)."""
    text = str(path)
    return text if path.is_absolute() or text.startswith(("..", "~")) else f"./{text}"


# ---------------------------------------------------------------- step 1-2: input

def select_input_type() -> str:
    return INPUT_TYPES[_choose("Select input type:", INPUT_TYPES) - 1]


def _path_problem(input_type: str, path: Path) -> str | None:
    if input_type == "Single PDF":
        return None if path.is_file() and path.suffix.lower() == ".pdf" else "That path is not a PDF file."
    if input_type == "Directory of PDFs":
        return None if path.is_dir() else "That path is not a directory."
    return None if path.is_file() and path.suffix.lower() == ".zip" else "That path is not a .zip archive."


def prompt_input_path(input_type: str) -> Path:
    label = {"Single PDF": "PDF path", "Directory of PDFs": "directory path", "ZIP archive": "ZIP path"}[input_type]
    default = DEFAULT_RESUMES_DIR if input_type == "Directory of PDFs" else None
    suffix = f" [{default}]" if default else ""
    while True:
        raw = input(f"Enter {label}{suffix}: ").strip() or (default or "")
        if not raw:
            print("Please enter a path.")
            continue
        path = _clean_path(raw)
        problem = _path_problem(input_type, path)
        if problem is None:
            return path
        print(problem)


# ---------------------------------------------------------------- step 3: output

def prompt_output_path(label: str, default: str) -> Path:
    """Ask for a file path; reject directories, and require confirmation before overwriting."""
    while True:
        raw = input(f"{label} [{default}]: ").strip() or default
        path = _clean_path(raw)
        if path.is_dir():
            print("That path is a directory. Please give a file name.")
        elif path.parent.exists() and not path.parent.is_dir():
            print(f"Cannot write there: {path.parent} is not a directory.")
        elif path.exists() and not _yes_no(f"{path.name} already exists. Overwrite?", default=False):
            continue
        else:
            return path


def prompt_output_options() -> tuple[bool, Path | None, Path | None]:
    """-> (show JSON in terminal, JSON file or None, TXT file or None)"""
    mode = _choose("Output options:", OUTPUT_MODES, "Select [1-3]")
    show_json = mode in (1, 2)
    if mode == 1:
        return show_json, None, None
    json_path = prompt_output_path("Output file", DEFAULT_JSON_PATH)
    text_path = None
    if _yes_no("Also save human-readable TXT?", default=False):
        text_path = prompt_output_path("Text file", DEFAULT_TEXT_PATH)
    return show_json, json_path, text_path


# ---------------------------------------------------------------- step 4: confirmation

def _configured(var: str) -> bool:
    return bool(os.environ.get(var, "").strip())


def show_confirmation(cfg: Config) -> bool:
    if cfg.json_path is None:
        output = "JSON (terminal only)"
    else:
        output = "JSON + file" if cfg.show_json else "File only"
    _heading("Screening Configuration")
    print(f"Input type     : {cfg.input_type}")
    print(f"Input          : {_shown(cfg.input_path)}\n")
    print(f"Output         : {output}")
    if cfg.json_path:
        print(f"JSON file      : {_shown(cfg.json_path)}")
    print(f"TXT export     : {_shown(cfg.text_path) if cfg.text_path else 'No'}\n")
    print(f"OpenRouter     : {'Configured' if _configured('OPENROUTER_API_KEY') else 'Not configured'}")
    print(f"GitHub token   : {'Configured' if _configured('GITHUB_TOKEN') else 'Not configured'}")
    print(f"\n{RULE}")
    if not _configured("OPENROUTER_API_KEY"):
        print("\nWarning:\nOpenRouter is not configured.\nScanned/image-only PDFs may fail extraction.")
    if not _configured("GITHUB_TOKEN"):
        print("\nNotice:\nGitHub enrichment will use unauthenticated public API access.\nRate limits may apply.")
    print()
    return _yes_no("Start Processing?", default=True)


# ---------------------------------------------------------------- processing + results

def show_processing(cfg: Config) -> None:
    _heading("Processing")
    print(f"Input:\n{_shown(cfg.input_path)}\n\nProcessing resumes...", flush=True)


def show_processing_summary(summary: BatchSummary) -> None:
    _heading("Processing Complete")
    print(f"Total resumes : {summary.total_files}")
    print(f"Ranked        : {summary.ranked}")
    print(f"Rejected      : {summary.rejected}")
    print(f"Failed        : {summary.failed}")
    print(f"Duplicates    : {summary.duplicates_skipped}\n")
    print(f"Duration      : {summary.duration_seconds}s\n\n{RULE}")


def show_json(payload: str) -> None:
    print(f"\nJSON Result\n{RULE}\n")
    print(payload)


# ---------------------------------------------------------------- saving / copying

def save_file(path: Path, content: str) -> bool:
    """Write UTF-8 with a trailing newline, creating parent directories. Reports problems, never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    except OSError as e:
        print(f"Could not save {path}: {e.strerror or e}")
        return False
    print(f"\nSaved:\n{_shown(path)}")
    return True


def _clipboard_command() -> list[str] | None:
    for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["clip"]):
        if shutil.which(cmd[0]):
            return cmd
    return None


def copy_to_clipboard(payload: str) -> bool:
    cmd = _clipboard_command()
    if cmd is None:
        print("Clipboard is unavailable. JSON remains available above.")
        return False
    try:
        subprocess.run(cmd, input=payload.encode("utf-8"), check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        print("Clipboard is unavailable. JSON remains available above.")
        return False
    print("JSON copied to clipboard.")
    return True


EXPORT_ACTIONS = ("Copy JSON payload", "Save JSON to file", "Save JSON and TXT", "Finish")


def prompt_export_action(summary: BatchSummary, payload: str) -> None:
    """Loop over export choices until Finish. Works on the in-memory result; never reruns screening."""
    while True:
        choice = _choose("What would you like to do?", EXPORT_ACTIONS, "Select [1-4]")
        if choice == 1:
            copy_to_clipboard(payload)
        elif choice == 2:
            save_file(prompt_output_path("Output file", DEFAULT_JSON_PATH), payload)
        elif choice == 3:
            json_path = prompt_output_path("Output file", DEFAULT_JSON_PATH)
            text_path = prompt_output_path("Text file", DEFAULT_TEXT_PATH)
            save_file(json_path, payload)
            save_file(text_path, render_text(summary))
        else:
            return


# ---------------------------------------------------------------- orchestration

def run_interactive(runner: Runner = screen_inputs) -> int:
    """Returns a process exit code. `runner` is the pipeline entry point (injectable for tests)."""
    try:
        return _run(runner)
    except KeyboardInterrupt:
        print("\n\nProcessing cancelled.")
        return 130
    except EOFError:
        print("\n\nInput closed. Interactive mode needs a terminal (use `docker run -it`), "
              "or pass --input/--output for non-interactive use.", file=sys.stderr)
        return 2


def _run(runner: Runner) -> int:
    print("# AI Resume Screening\n\nInteractive Screening Workflow")
    input_type = select_input_type()
    input_path = prompt_input_path(input_type)
    show, json_path, text_path = prompt_output_options()
    cfg = Config(input_type, input_path, show, json_path, text_path)

    if not show_confirmation(cfg):
        print("\nProcessing cancelled.")
        return 0

    show_processing(cfg)
    try:
        summary = runner(cfg.input_path)
    except FileNotFoundError as e:   # the path was valid a moment ago; report it like the flag-based CLI
        print(f"error: {e}", file=sys.stderr)
        return 2
    payload = summary_json(summary)

    show_processing_summary(summary)
    if cfg.show_json:
        show_json(payload)
    if cfg.json_path:
        save_file(cfg.json_path, payload)
    if cfg.text_path:
        save_file(cfg.text_path, render_text(summary))

    prompt_export_action(summary, payload)
    return 0
