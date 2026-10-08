"""End-to-end (synthetic): ingest PDFs -> fake extractor -> screen -> JSON. No network, no LLM."""
import json

from src.models import ExtractedResume, ScreeningStatus
from src.pipeline import extraction_not_implemented, run_batch, write_summary

from .factories import PLATFORM_JOB, STRONG_PROJECT
from .test_ingestion import LINES, make_pdf


def fake_extractor(doc):
    # Stand-in for the later LLM step. Candidates named "java_*" have no Python/AI.
    if doc.source_file.startswith("java"):
        return ExtractedResume(source_file=doc.source_file, raw_text=doc.text, skills=["Java"])
    return ExtractedResume(source_file=doc.source_file, raw_text=doc.text, skills=["Python"],
                           projects=[STRONG_PROJECT.model_copy(update={"evidence": [LINES[0]]})],
                           experience=[PLATFORM_JOB.model_copy(update={"evidence": [LINES[1]]})])


def test_synthetic_batch_end_to_end(tmp_path):
    make_pdf(tmp_path / "good.pdf", LINES)
    (tmp_path / "dup.pdf").write_bytes((tmp_path / "good.pdf").read_bytes())
    make_pdf(tmp_path / "java_dev.pdf", [l.replace("Python", "Java") for l in LINES])
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf")

    summary = run_batch(tmp_path, fake_extractor)
    by = {r.source_file: r for r in summary.results}
    assert (summary.ranked, summary.rejected, summary.failed, summary.duplicates_skipped) == (1, 1, 1, 1)
    ranked = [r for r in summary.results if r.status is ScreeningStatus.RANKED]
    assert len(ranked) == 1 and ranked[0].rank == 1 and ranked[0].score.total > 0
    rejected = by["java_dev.pdf"]
    assert rejected.status is ScreeningStatus.REJECTED and rejected.score is None and rejected.rank is None
    assert by["broken.pdf"].status is ScreeningStatus.FAILED

    out = tmp_path / "out" / "results.json"
    write_summary(summary, out)
    data = json.loads(out.read_text())
    assert data["ranked"] == 1 and "raw_text" not in out.read_text()


def test_extraction_failure_is_candidate_level(tmp_path):
    make_pdf(tmp_path / "good.pdf", LINES)
    summary = run_batch(tmp_path, extraction_not_implemented)
    assert summary.failed == 1 and "extraction failed" in summary.results[0].error
