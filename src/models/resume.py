"""Document facts only. Nothing here is a judgement about the candidate."""
import re
from typing import Literal

from pydantic import BaseModel, Field


class ExtractedProject(BaseModel):
    name: str = Field(description="Project title exactly as written")
    description: str = Field("", description="Project description, wording preserved (bullets joined)")
    technologies: list[str] = Field(default_factory=list, description="Technologies named for this project")
    evidence: list[str] = Field(
        default_factory=list,
        description="1-3 short VERBATIM snippets copied from this project's text in the resume")


class ExtractedExperience(BaseModel):
    role: str = Field("", description="Job title as written")
    company: str = Field("", description="Employer / organisation as written")
    description: str = Field("", description="Role description, wording preserved (bullets joined)")
    technologies: list[str] = Field(default_factory=list, description="Technologies named for this role")
    evidence: list[str] = Field(
        default_factory=list,
        description="1-3 short VERBATIM snippets copied from this role's text in the resume")


class ResumeExtraction(BaseModel):
    """The contract for LLM output (its JSON schema is generated from this class).

    Deliberately has no eligibility, score, rank, penalty or opinion fields.
    """
    name: str | None = Field(None, description="Candidate name, or null if not visible")
    email: str | None = Field(None, description="Email address, or null if not visible")
    github_url: str | None = Field(None, description="GitHub profile URL as written, or null")
    skills: list[str] = Field(default_factory=list, description="Skills exactly as listed in the resume")
    projects: list[ExtractedProject] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list, description="One entry per education line, as written")
    experience: list[ExtractedExperience] = Field(default_factory=list)
    raw_text: str = Field(
        "", description="Faithful transcription of ALL meaningful resume text, nothing summarised away")


class ExtractedResume(ResumeExtraction):
    """A ResumeExtraction plus provenance that only code sets."""
    source_file: str
    extraction_method: Literal["text", "llm_vision"] = "text"

    @property
    def github_username(self) -> str | None:
        """Derived by code from github_url; never trusted from the model."""
        if not self.github_url:
            return None
        m = re.search(r"github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))", self.github_url, re.I)
        return m.group(1) if m else None
