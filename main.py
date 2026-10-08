"""CLI entrypoint: python main.py --input ./resumes --output ./output/results.json"""
import argparse
import sys
from pathlib import Path

from src.pipeline import run_batch, write_summary


def main() -> int:
    p = argparse.ArgumentParser(description="AI resume screening & ranking")
    p.add_argument("--input", default="./resumes", type=Path, help="Directory of resume PDFs")
    p.add_argument("--output", default="./output/results.json", type=Path, help="Result JSON path")
    args = p.parse_args()

    try:
        summary = run_batch(args.input)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    write_summary(summary, args.output)
    print(f"{summary.total_files} files: {summary.ranked} ranked, {summary.rejected} rejected, "
          f"{summary.failed} failed, {summary.duplicates_skipped} duplicates skipped -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
