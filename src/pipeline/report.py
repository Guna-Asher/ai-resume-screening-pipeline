"""Human-readable rendering of a BatchSummary. Presentation only: all facts come from the JSON model."""
from src.models import BatchSummary, ScreeningStatus


def render_text(summary: BatchSummary) -> str:
    s = summary
    out = [
        "AI RESUME SCREENING RESULTS", "=" * 27,
        f"Files: {s.total_files}   Ranked: {s.ranked}   Rejected: {s.rejected}   Failed: {s.failed}   "
        f"Duplicates skipped: {s.duplicates_skipped}   Duration: {s.duration_seconds}s", "",
    ]
    ranked = [r for r in s.results if r.status is ScreeningStatus.RANKED]
    out.append("RANKED")
    if not ranked:
        out.append("  (none)")
    for r in ranked:
        sc = r.score
        name = (r.candidate.name if r.candidate and r.candidate.name else r.source_file)
        out.append(f"{r.rank:>3}. {name} [{r.source_file}]  total {sc.total:g}/100  "
                   f"(AI {sc.ai_project_depth:g}/40, Python {sc.python_backend:g}/30, Cloud {sc.cloud_fullstack:g}/15, "
                   f"GitHub {sc.github_activity:g}/10, Eng {sc.engineering_depth:g}/5, penalty -{sc.penalty:g})")
        if r.project_summary:
            out.append(f"       projects: {r.project_summary}")
        out += [f"       {n}" for n in sc.notes]
        out += [f"       concern: {c}" for c in r.concerns]
    for title, status in (("REJECTED", ScreeningStatus.REJECTED), ("FAILED", ScreeningStatus.FAILED)):
        out += ["", title]
        items = [r for r in s.results if r.status is status]
        if not items:
            out.append("  (none)")
        for r in items:
            reasons = r.eligibility.rejection_reasons if r.eligibility else [r.error or "unknown error"]
            out.append(f"  - {r.source_file}: " + "; ".join(reasons))
    if s.ignored_files:
        out += ["", "IGNORED (not PDF)", *[f"  - {n}" for n in s.ignored_files]]
    return "\n".join(out) + "\n"
