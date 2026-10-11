"""Job request and response models (docs/contracts.md section 5, "Job")."""
from typing import Literal

from pydantic import BaseModel


class JobCreate(BaseModel):
    title: str | None = None  # required; checked in the route to keep "title is required"
    description_text: str | None = None
    scoring_template_id: int | None = None


class JobUpdate(BaseModel):
    """Only the fields sent are changed; null title or description_text is ignored."""
    title: str | None = None
    description_text: str | None = None
    scoring_template_id: int | None = None


class JobOut(BaseModel):
    id: int
    title: str
    description: str
    required_skills: list[str]
    preferred_skills: list[str]
    min_experience_years: float | None
    required_education: str | None
    created_at: str | None
    candidates_count: int
    status: Literal["Open", "Filled"]
