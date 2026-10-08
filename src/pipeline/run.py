"""End-to-end run: ingest -> extract -> ground -> screen -> rank -> JSON."""
import time
from pathlib import Path
from typing import Callable

from src.extraction import ground_resume
from src.ingestion import ingest_directory
from src.models import BatchSummary, ExtractedResume, IngestedDocument, IngestionStatus

from .batch import failed_result, failures_from_ingestion, rank, safe_screen, summarize

Extractor = Callable[[IngestedDocument], ExtractedResume]


def extraction_not_implemented(doc: IngestedDocument) -> ExtractedResume:
    raise NotImplementedError("LLM extraction is not implemented yet")


def run_batch(input_dir: Path, extractor: Extractor = extraction_not_implemented) -> BatchSummary:
    start = time.monotonic()
    docs = ingest_directory(input_dir)
    results = failures_from_ingestion(docs)
    for doc in docs:
        if doc.status is not IngestionStatus.OK:
            continue
        try:
            resume = ground_resume(extractor(doc))
        except Exception as e:  # extraction failure is candidate-level
            results.append(failed_result(doc.source_file, f"extraction failed: {type(e).__name__}: {e}"))
            continue
        results.append(safe_screen(resume))
    duplicates = sum(d.status is IngestionStatus.DUPLICATE for d in docs)
    return summarize(rank(results), len(docs), duplicates, time.monotonic() - start)


def write_summary(summary: BatchSummary, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = summary.model_dump_json(indent=2, exclude={"results": {"__all__": {"candidate": {"raw_text"}}}})
    output_path.write_text(data, encoding="utf-8")
