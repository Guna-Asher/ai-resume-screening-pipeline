from pydantic import BaseModel, Field, computed_field


class ScoreBreakdown(BaseModel):
    """100-point model. Each category is bounded by its weight; total is computed."""
    ai_project_depth: float = Field(0, ge=0, le=40)
    python_backend: float = Field(0, ge=0, le=30)
    cloud_fullstack: float = Field(0, ge=0, le=15)
    github_activity: float = Field(0, ge=0, le=10)
    engineering_depth: float = Field(0, ge=0, le=5)
    penalty: float = Field(0, ge=0, le=15, description="Thin-AI-project penalty: 0/5/10/15")
    notes: list[str] = Field(default_factory=list, description="Why each point was awarded")

    @computed_field
    @property
    def total(self) -> float:
        raw = (self.ai_project_depth + self.python_backend + self.cloud_fullstack
               + self.github_activity + self.engineering_depth - self.penalty)
        return round(max(0.0, min(100.0, raw)), 2)
