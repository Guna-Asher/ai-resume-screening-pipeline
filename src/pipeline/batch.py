"""Orchestration with per-candidate error isolation."""
import logging
from collections.abc import Callable

from src.models import (BatchSummary, ExtractedResume, GitHubEnrichment, GitHubStatus, IngestedDocument,
                        IngestionStatus, ScoreBreakdown, ScreeningResult, ScreeningStatus)
from src.screening import build_project_summary, check_eligibility, score_resume


logger = logging.getLogger(__name__)

UNPARSEABLE_MESSAGE = ("Unable to extract structured resume sections. The PDF was readable, but its layout "
                       "could not be reliably parsed.")
INTERNAL_MESSAGE = "An unexpected error occurred while processing this resume."
INGESTION_MESSAGES = {
    "unreadable_pdf": "The PDF could not be read. It may be corrupted, encrypted, or not a valid PDF.",
    "file_unreadable": "The file could not be read.",
}


class CandidateFailure(Exception):
    """A known, user-explainable reason a resume cannot be screened."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def failed_result(source_file: str, message: str, code: str = "internal_error") -> ScreeningResult:
    return ScreeningResult(source_file=source_file, status=ScreeningStatus.FAILED, error=message, error_code=code)


Enricher = Callable[[str | None], GitHubEnrichment]


def _enrich(resume: ExtractedResume, enricher: Enricher | None) -> GitHubEnrichment | None:
    if enricher is None:
        return None
    try:
        return enricher(resume.github_username)
    except Exception as e:  # contract: enrichers never raise; if one does, GitHub still must not fail the candidate
        return GitHubEnrichment(status=GitHubStatus.ERROR, username=resume.github_username,
                                error=f"GitHub enrichment failed: {type(e).__name__}")


def _concerns(score: ScoreBreakdown, github: GitHubEnrichment | None) -> list[str]:
    concerns = [n for n in score.notes if n.startswith("-")]
    if github is not None and github.status is not GitHubStatus.OK:
        concerns.append("No GitHub profile on resume" if github.status is GitHubStatus.NOT_PROVIDED
                        else f"GitHub not scored: {github.error}")
    return concerns


def screen_resume(resume: ExtractedResume, enricher: Enricher | None = None) -> ScreeningResult:
    if not resume.raw_text.strip() or not (resume.projects or resume.experience or resume.skills):
        raise CandidateFailure("unparseable_layout", UNPARSEABLE_MESSAGE)
    summary = build_project_summary(resume)
    eligibility = check_eligibility(resume)
    if not eligibility.eligible:   # rejected candidates are never scored, ranked or sent to GitHub
        return ScreeningResult(source_file=resume.source_file, status=ScreeningStatus.REJECTED,
                               candidate=resume, eligibility=eligibility, project_summary=summary)
    github = _enrich(resume, enricher)
    score = score_resume(resume, github)
    return ScreeningResult(source_file=resume.source_file, status=ScreeningStatus.RANKED,
                           candidate=resume, eligibility=eligibility, score=score, github=github,
                           project_summary=summary, concerns=_concerns(score, github))


def failures_from_ingestion(docs: list[IngestedDocument]) -> list[ScreeningResult]:
    """Unreadable PDFs. (NEEDS_FALLBACK documents go to the extractor, not here.)"""
    out = []
    for d in docs:
        if d.status is IngestionStatus.ERROR:
            logger.debug("ingestion failed for %s: %s", d.source_file, d.error)
            code = d.error_code or "internal_error"
            out.append(failed_result(d.source_file, INGESTION_MESSAGES.get(code, INTERNAL_MESSAGE), code))
    return out


def rank(results: list[ScreeningResult]) -> list[ScreeningResult]:
    """Rank only RANKED results: score desc, then AI, Python, source_file for stable ties."""
    ranked = sorted((r for r in results if r.status is ScreeningStatus.RANKED),
                    key=lambda r: (-r.score.total, -r.score.ai_project_depth,
                                   -r.score.python_backend, r.source_file))
    for i, r in enumerate(ranked, 1):
        r.rank = i
    return ranked + [r for r in results if r.status is not ScreeningStatus.RANKED]


def safe_screen(resume: ExtractedResume, enricher: Enricher | None = None) -> ScreeningResult:
    try:
        return screen_resume(resume, enricher)
    except CandidateFailure as e:
        return failed_result(resume.source_file, str(e), e.code)
    except Exception:  # one bad candidate must never stop the batch; the cause goes to the log, not the output
        logger.warning("unexpected error while screening %s", resume.source_file, exc_info=True)
        return failed_result(resume.source_file, INTERNAL_MESSAGE)


def screen_batch(resumes: list[ExtractedResume], enricher: Enricher | None = None) -> list[ScreeningResult]:
    return rank([safe_screen(r, enricher) for r in resumes])


def summarize(results: list[ScreeningResult], total_files: int, duplicates: int,
              duration: float, ignored: list[str] | None = None) -> BatchSummary:
    count = lambda s: sum(r.status is s for r in results)  # noqa: E731
    llm_used = sum(r.candidate is not None and r.candidate.extraction_method == "llm_vision"
                   for r in results)
    return BatchSummary(total_files=total_files, ranked=count(ScreeningStatus.RANKED),
                        rejected=count(ScreeningStatus.REJECTED), failed=count(ScreeningStatus.FAILED),
                        duplicates_skipped=duplicates, ignored_files=ignored or [], llm_fallback_extractions=llm_used,
                        duration_seconds=round(duration, 2),
                        results=results)
