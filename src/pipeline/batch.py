"""Orchestration with per-candidate error isolation."""
from src.models import (BatchSummary, ExtractedResume, IngestedDocument, IngestionStatus,
                        ScreeningResult, ScreeningStatus)
from src.screening import check_eligibility, score_resume


def failed_result(source_file: str, error: str) -> ScreeningResult:
    return ScreeningResult(source_file=source_file, status=ScreeningStatus.FAILED, error=error)


def screen_resume(resume: ExtractedResume) -> ScreeningResult:
    if not resume.raw_text.strip() or not (resume.projects or resume.experience or resume.skills):
        raise ValueError("invalid extracted data: no source text or no extracted content")
    summary = "; ".join(p.name for p in resume.projects)
    eligibility = check_eligibility(resume)
    if not eligibility.eligible:
        return ScreeningResult(source_file=resume.source_file, status=ScreeningStatus.REJECTED,
                               candidate=resume, eligibility=eligibility, project_summary=summary)
    return ScreeningResult(source_file=resume.source_file, status=ScreeningStatus.RANKED,
                           candidate=resume, eligibility=eligibility, score=score_resume(resume),
                           project_summary=summary)


def failures_from_ingestion(docs: list[IngestedDocument]) -> list[ScreeningResult]:
    """Unreadable PDFs. (NEEDS_FALLBACK documents go to the extractor, not here.)"""
    return [failed_result(d.source_file, d.error or "ingestion error")
            for d in docs if d.status is IngestionStatus.ERROR]


def rank(results: list[ScreeningResult]) -> list[ScreeningResult]:
    """Rank only RANKED results: score desc, then AI, Python, source_file for stable ties."""
    ranked = sorted((r for r in results if r.status is ScreeningStatus.RANKED),
                    key=lambda r: (-r.score.total, -r.score.ai_project_depth,
                                   -r.score.python_backend, r.source_file))
    for i, r in enumerate(ranked, 1):
        r.rank = i
    return ranked + [r for r in results if r.status is not ScreeningStatus.RANKED]


def safe_screen(resume: ExtractedResume) -> ScreeningResult:
    try:
        return screen_resume(resume)
    except Exception as e:  # one bad candidate must never stop the batch
        return failed_result(resume.source_file, f"{type(e).__name__}: {e}")


def screen_batch(resumes: list[ExtractedResume]) -> list[ScreeningResult]:
    return rank([safe_screen(r) for r in resumes])


def summarize(results: list[ScreeningResult], total_files: int, duplicates: int,
              duration: float) -> BatchSummary:
    count = lambda s: sum(r.status is s for r in results)  # noqa: E731
    llm_used = sum(r.candidate is not None and r.candidate.extraction_method == "llm_vision"
                   for r in results)
    return BatchSummary(total_files=total_files, ranked=count(ScreeningStatus.RANKED),
                        rejected=count(ScreeningStatus.REJECTED), failed=count(ScreeningStatus.FAILED),
                        duplicates_skipped=duplicates, llm_fallback_extractions=llm_used,
                        duration_seconds=round(duration, 2),
                        results=results)
