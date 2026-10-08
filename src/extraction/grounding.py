"""Evidence grounding: keep only extracted facts that can be found in the source text.

Matching ignores case, punctuation, bullets and line breaks, because PDF text
extraction mangles whitespace.
"""
import re

from src.models import ExtractedResume

MIN_SNIPPET_CHARS = 8


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9+#]+", " ", text.lower()).split())


def _in(haystack: str, needle: str) -> bool:
    n = normalize(needle)
    return bool(n) and f" {n} " in f" {haystack} "


def _grounded(snippets: list[str], haystack: str) -> list[str]:
    return [s for s in snippets if len(normalize(s)) >= MIN_SNIPPET_CHARS and _in(haystack, s)]


def ground_resume(resume: ExtractedResume) -> ExtractedResume:
    """Drop skills, projects, jobs and URLs the source text does not support."""
    hay = normalize(resume.raw_text)
    projects, experience = [], []
    for p in resume.projects:
        ev = _grounded(p.evidence, hay)
        if ev:
            projects.append(p.model_copy(update={"evidence": ev}))
    for e in resume.experience:
        ev = _grounded(e.evidence, hay)
        if ev:
            experience.append(e.model_copy(update={"evidence": ev}))
    return resume.model_copy(update={
        "skills": [s for s in resume.skills if _in(hay, s)],
        "projects": projects,
        "experience": experience,
        "github_url": resume.github_url if resume.github_url and _in(hay, resume.github_url) else None,
    })
