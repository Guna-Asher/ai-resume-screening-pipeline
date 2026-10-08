"""One entry point for CLI and web: sources -> ingest -> extract -> ground -> screen -> rank."""
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from src.extraction import ExtractionError, ResumeExtractor, ground_resume
from src.enrichment import GitHubEnricher
from src.ingestion import InputLimits, collect_inputs, ingest_paths
from src.llm import OpenRouterClient
from src.models import BatchSummary, ExtractedResume, IngestedDocument, IngestionStatus

from .batch import Enricher, failed_result, failures_from_ingestion, rank, safe_screen, summarize

Extractor = Callable[[IngestedDocument], ExtractedResume]


def run_batch(sources: Path | Sequence[Path], extractor: Extractor, enricher: Enricher | None = None,
              limits: InputLimits | None = None) -> BatchSummary:
    """Screen every PDF reachable from `sources` (directories, PDFs, ZIPs, or a mix).

    Raises FileNotFoundError for a missing source. Everything else is reported per candidate.
    ZIP contents are extracted to a temporary directory that is removed when the run ends.
    """
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="screening-") as workdir:
        collected = collect_inputs(sources, Path(workdir), limits)
        docs = ingest_paths(collected.pdfs)
        results = [failed_result(p.name, p.message) for p in collected.problems]
        results += failures_from_ingestion(docs)
        for doc in docs:
            if doc.status not in (IngestionStatus.OK, IngestionStatus.NEEDS_FALLBACK):
                continue
            try:
                resume = ground_resume(extractor(doc))
            except Exception as e:  # extraction failure is candidate-level
                msg = str(e) if isinstance(e, ExtractionError) else f"{type(e).__name__}: {e}"
                results.append(failed_result(doc.source_file, f"extraction failed: {msg}"))
                continue
            results.append(safe_screen(resume, enricher))
    duplicates = sum(d.status is IngestionStatus.DUPLICATE for d in docs)
    return summarize(rank(results), len(docs) + len(collected.problems), duplicates,
                     time.monotonic() - start, collected.ignored)


def screen_inputs(sources: Path | Sequence[Path], limits: InputLimits | None = None) -> BatchSummary:
    """run_batch wired with the real services, configured from the environment (CLI and web both use this)."""
    return run_batch(sources, ResumeExtractor(OpenRouterClient.from_env()), GitHubEnricher.from_env(),
                     limits or InputLimits.from_env())


def summary_json(summary: BatchSummary) -> str:
    """The canonical JSON result. The CLI file and the web response are exactly this string."""
    return summary.model_dump_json(indent=2, exclude={"results": {"__all__": {"candidate": {"raw_text"}}}})


def write_summary(summary: BatchSummary, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(summary_json(summary), encoding="utf-8")
