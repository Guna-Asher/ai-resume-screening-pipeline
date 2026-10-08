"""CLI: python main.py --input <dir | file.pdf | file.zip> --output ./output/results.json [--text-output FILE]"""
import argparse
import sys
from pathlib import Path

from src.pipeline import render_text, screen_inputs, write_summary


def main() -> int:
    p = argparse.ArgumentParser(description="AI resume screening & ranking")
    p.add_argument("--input", default="./resumes", type=Path, help="Directory of PDFs, a single PDF, or a ZIP")
    p.add_argument("--output", default="./output/results.json", type=Path, help="Result JSON path (source of truth)")
    p.add_argument("--text-output", type=Path, help="Optional human-readable rendering of the same result")
    args = p.parse_args()

    try:
        summary = screen_inputs(args.input)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    write_summary(summary, args.output)
    if args.text_output:
        args.text_output.parent.mkdir(parents=True, exist_ok=True)
        args.text_output.write_text(render_text(summary), encoding="utf-8")
    print(f"{summary.total_files} files: {summary.ranked} ranked, {summary.rejected} rejected, "
          f"{summary.failed} failed, {summary.duplicates_skipped} duplicates skipped, "
          f"{summary.llm_fallback_extractions} via LLM fallback -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
