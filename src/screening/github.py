"""GitHub points (max 10) from already-fetched facts. Pure and deterministic; no network here.

Recent activity (0-5): relevant repos pushed within the recent window: 1 -> 2, 2 -> 3, 3 -> 4, 4+ -> 5.
Relevance (0-5):       Python repos (max 2) + AI/LLM/agent repos (max 2) + 1 if one of them is maintained.
Stars are deliberately ignored. Anything other than a successful lookup scores 0.
"""
from src.models import GitHubEnrichment, GitHubStatus

_ACTIVITY_POINTS = {0: 0, 1: 2, 2: 3, 3: 4}


def github_points(gh: GitHubEnrichment | None) -> tuple[float, list[str]]:
    if gh is None or gh.status is not GitHubStatus.OK:
        return 0.0, []
    activity = float(_ACTIVITY_POINTS.get(gh.recently_active_repos, 5))
    relevance = float(min(2, gh.python_repos) + min(2, gh.ai_repos) + (1 if gh.maintained else 0))
    notes = []
    if activity:
        notes.append(f"+{activity:g} github activity ({gh.recently_active_repos} repos pushed in {gh.recent_days}d)")
    if relevance:
        notes.append(f"+{relevance:g} github relevance ({gh.python_repos} Python, {gh.ai_repos} AI repos"
                     f"{', maintained' if gh.maintained else ''})")
    return activity + relevance, notes
