"""Document facts only. The LLM (later step) fills these; it never judges."""
import re

from pydantic import BaseModel, Field


class ExtractedProject(BaseModel):
    name: str
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)  # snippets copied from the resume


class ExtractedExperience(BaseModel):
    role: str = ""
    company: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class ExtractedResume(BaseModel):
    source_file: str
    name: str | None = None
    email: str | None = None
    github_url: str | None = None
    skills: list[str] = Field(default_factory=list)
    projects: list[ExtractedProject] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    experience: list[ExtractedExperience] = Field(default_factory=list)
    raw_text: str = ""

    @property
    def github_username(self) -> str | None:
        """Derived by code from github_url; never trusted from the model."""
        if not self.github_url:
            return None
        m = re.search(r"github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))", self.github_url, re.I)
        return m.group(1) if m else None
