from pydantic import BaseModel, Field


class EligibilityResult(BaseModel):
    """Deterministic verdict from src/screening/eligibility.py."""
    eligible: bool
    has_python_evidence: bool = False
    has_ai_evidence: bool = False
    matched_signals: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
