from enum import Enum

from pydantic import BaseModel, Field


class GitHubStatus(str, Enum):
    NOT_PROVIDED = "not_provided"
    OK = "ok"
    NOT_FOUND = "not_found"      # no such user, or profile not public
    RATE_LIMITED = "rate_limited"
    ERROR = "error"              # timeout, network failure, unexpected response


class GitHubEnrichment(BaseModel):
    """Public-API facts only. Any failure just means 0 GitHub points; it never fails a candidate.

    "Relevant" repos are the user's own (not forks), not archived and not empty.
    """
    status: GitHubStatus = GitHubStatus.NOT_PROVIDED
    username: str | None = None
    recent_days: int = 90
    public_repos: int = 0
    relevant_repos: int = 0
    recently_active_repos: int = 0   # relevant repos pushed within GITHUB_RECENT_DAYS
    python_repos: int = 0            # relevant repos whose main language is Python
    ai_repos: int = 0                # relevant repos whose name/description/topics mention AI/LLM/RAG/agents
    maintained: bool = False         # a Python/AI repo pushed within the last 365 days
    total_stars: int = 0             # informational only: NOT used for scoring
    top_languages: list[str] = Field(default_factory=list)
    error: str | None = None
