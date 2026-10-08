"""Opt-in smoke test against the REAL OpenRouter API. Not part of pytest / CI.

    docker run --rm --env-file .env ai-resume-screening python scripts/smoke_openrouter.py

Skips (exit 0) unless OPENROUTER_API_KEY is set. Never prints the key.
Builds a synthetic image-only resume PDF, runs the fallback extraction, validates the result.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extraction import extract_with_llm, ground_resume  # noqa: E402
from src.llm import OpenRouterClient  # noqa: E402
from src.models import IngestionStatus  # noqa: E402
from tests.pdf_fixtures import RESUME_LINES, ingest_dir, make_scanned_pdf  # noqa: E402


def main() -> int:
    client = OpenRouterClient.from_env()
    if client is None:
        print("SKIPPED: OPENROUTER_API_KEY is not set")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        make_scanned_pdf(Path(tmp) / "synthetic_scan.pdf", RESUME_LINES)
        doc = ingest_dir(Path(tmp))[0]
        assert doc.status is IngestionStatus.NEEDS_FALLBACK, "fixture should have no text layer"
        print(f"model: {client.model}")
        extracted = extract_with_llm(doc, client)        # raises ExtractionError on any failure
    grounded = ground_resume(extracted)
    print(f"extracted name: {extracted.name!r}")
    print(f"projects: {len(extracted.projects)} extracted, {len(grounded.projects)} grounded in raw_text")
    print(f"experience: {len(extracted.experience)}, skills: {len(extracted.skills)}")
    print("OK: structured response validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
