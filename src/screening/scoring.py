"""Deterministic 100-point score. Evidence in project/job text is required for credit.

Credit rule for a signal worth N points:
  * found in an entry that also contains an implementation verb (built, implemented...) -> N
  * found only as a mention in an entry                                                  -> N / 2
  * found only in the skills list, or nowhere                                            -> 0
(Python is the one exception: skills-only Python earns PYTHON_SKILLS_ONLY points.)

Final = sum(categories) - thin-AI-project penalty, clamped to 0..100.
"""
from src.models import ExtractedResume, GitHubEnrichment, ScoreBreakdown

from .github import github_points
from .signals import MEANINGFUL, THIN_DESCRIPTION_WORDS, Document, build_documents, python_in_skills

PYTHON_SKILLS_ONLY = 3.0  # < half of the 12 Python points: a skills list is not implementation

# (signal, points) per category. Caps: AI 40, Python/backend 30, cloud 15, engineering 5.
AI_COMPONENTS = [("llm", 10), ("rag", 6), ("tools", 6), ("orch_generic", 6), ("eval", 5), ("data", 7)]
FRAMEWORK_ONLY_ORCH = 3  # naming LangChain/LangGraph/etc. earns at most half the orchestration points
BACKEND_COMPONENTS = [("python", 12), ("backend", 8), ("async", 4), ("database", 6)]
CLOUD_COMPONENTS = [("cloud", 5), ("docker", 5), ("frontend", 5)]
ENGINEERING_COMPONENTS = [("testing", 1), ("modular", 1), ("reliability", 1), ("cache_queue", 1),
                          ("observability", 1)]


def _credit(docs: list[Document], signal: str, points: float) -> tuple[float, str | None]:
    hits = [d for d in docs if signal in d.signals]
    if not hits:
        return 0.0, None
    if any(d.has_implementation for d in hits):
        return float(points), f"+{points:g} {signal} (implementation evidence)"
    return points / 2, f"+{points / 2:g} {signal} (mention only)"


def _sum(docs: list[Document], components: list[tuple[str, float]], notes: list[str]) -> float:
    total = 0.0
    for signal, points in components:
        got, note = _credit(docs, signal, points)
        total += got
        if note:
            notes.append(note)
    return total


def score_ai(docs: list[Document], notes: list[str]) -> float:
    ai_docs = [d for d in docs if d.is_ai]
    total = _sum(ai_docs, [c for c in AI_COMPONENTS if c[0] != "orch_generic"], notes)
    generic, g_note = _credit(ai_docs, "orch_generic", 6)
    named, n_note = _credit(ai_docs, "frameworks", FRAMEWORK_ONLY_ORCH)
    if generic >= named:
        total += generic
        if g_note:
            notes.append(g_note)
    else:
        total += named
        notes.append(n_note.replace("frameworks", "orchestration framework"))
    return min(total, 40.0)


def score_python_backend(resume: ExtractedResume, docs: list[Document], notes: list[str]) -> float:
    total = _sum(docs, BACKEND_COMPONENTS, notes)
    if not any("python" in d.signals for d in docs) and python_in_skills(resume):
        total += PYTHON_SKILLS_ONLY
        notes.append(f"+{PYTHON_SKILLS_ONLY:g} python (skills list only)")
    return min(total, 30.0)


def score_cloud_fullstack(docs: list[Document], notes: list[str]) -> float:
    return min(_sum(docs, CLOUD_COMPONENTS, notes), 15.0)


def score_engineering(docs: list[Document], notes: list[str]) -> float:
    return min(_sum(docs, ENGINEERING_COMPONENTS, notes), 5.0)


def thin_ai_penalty(docs: list[Document], notes: list[str]) -> float:
    """One penalty per candidate, judged on the strongest AI project/job.

    15: only a bare LLM/API call (no retrieval, tools, workflow, eval, data or backend logic)
    10: exactly one meaningful signal beyond the LLM call
     5: two or more signals but weak detail (no implementation verb, tutorial-like, or very short)
     0: meaningful implementation depth
    """
    ai_docs = [d for d in docs if d.is_ai]
    if not ai_docs:
        return 0.0
    # Strongest project wins; a weaker secondary AI project can never raise the penalty.
    best = max(ai_docs, key=lambda d: (len(d.signals & MEANINGFUL), d.has_implementation,
                                       not d.is_tutorial_like, d.description_words))
    n = len(best.signals & MEANINGFUL)
    if n == 0:
        penalty, why = 15.0, "only a bare LLM/API call"
    elif n == 1:
        penalty, why = 10.0, "only one meaningful signal beyond the LLM call"
    elif not best.has_implementation or best.is_tutorial_like or best.description_words < THIN_DESCRIPTION_WORDS:
        penalty, why = 5.0, "weak implementation detail or tutorial-like"
    else:
        return 0.0
    notes.append(f"-{penalty:g} thin AI project '{best.label}': {why}")
    return penalty


def score_resume(resume: ExtractedResume, github: GitHubEnrichment | None = None) -> ScoreBreakdown:
    """Call only for eligible candidates. `github` is optional; without a successful lookup it scores 0."""
    docs = build_documents(resume)
    notes: list[str] = []
    ai = score_ai(docs, notes)
    backend = score_python_backend(resume, docs, notes)
    cloud = score_cloud_fullstack(docs, notes)
    gh_points, gh_notes = github_points(github)
    notes += gh_notes
    return ScoreBreakdown(
        ai_project_depth=ai, python_backend=backend, cloud_fullstack=cloud,
        github_activity=gh_points,
        engineering_depth=score_engineering(docs, notes),
        penalty=thin_ai_penalty(docs, notes),
        notes=notes,
    )
