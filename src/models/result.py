from enum import Enum

from pydantic import BaseModel, Field

from .eligibility import EligibilityResult
from .enrichment import GitHubEnrichment
from .resume import ExtractedResume
from .score import ScoreBreakdown


class ScreeningStatus(str, Enum):
    RANKED = "ranked"      # eligible and scored
    REJECTED = "rejected"  # failed a hard rule; never scored or ranked
    FAILED = "failed"      # unreadable / invalid data; fail closed


class ScreeningResult(BaseModel):
    source_file: str
    status: ScreeningStatus
    candidate: ExtractedResume | None = None
    eligibility: EligibilityResult | None = None
    score: ScoreBreakdown | None = None   # None unless RANKED
    github: GitHubEnrichment | None = None
    project_summary: str = ""
    rank: int | None = None               # None unless RANKED
    error: str | None = None              # set only for FAILED


class BatchSummary(BaseModel):
    total_files: int = 0
    ranked: int = 0
    rejected: int = 0
    failed: int = 0
    duplicates_skipped: int = 0
    duration_seconds: float = 0.0
    results: list[ScreeningResult] = Field(default_factory=list)
