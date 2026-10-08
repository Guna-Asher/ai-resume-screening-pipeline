from enum import Enum

from pydantic import BaseModel, Field


class GitHubStatus(str, Enum):
    NOT_PROVIDED = "not_provided"
    OK = "ok"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


class GitHubEnrichment(BaseModel):
    """Public-API facts only. Failure never disqualifies a candidate."""
    status: GitHubStatus = GitHubStatus.NOT_PROVIDED
    username: str | None = None
    public_repos: int = 0
    python_repos: int = 0
    total_stars: int = 0
    recently_active_repos: int = 0   # pushed within the last 90 days
    top_languages: list[str] = Field(default_factory=list)
    error: str | None = None
