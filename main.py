"""CLI entrypoint: python main.py --input ./resumes --output ./output/results.json"""
import argparse


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AI resume screening & ranking")
    p.add_argument("--input", default="./resumes", help="Directory of resume PDFs")
    p.add_argument("--output", default="./output/results.json", help="Result JSON path")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    raise NotImplementedError("Pipeline not implemented yet")  # -> src.pipeline.run_batch


if __name__ == "__main__":
    main()
