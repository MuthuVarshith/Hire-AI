"""Scoring template models (docs/contracts.md section 5, "Template")."""
from typing import Any

from pydantic import BaseModel, field_validator

from app.schemas.common import request_error

WEIGHTS = ("semantic_weight", "skill_weight", "experience_weight", "education_weight")


def _weight(value: Any) -> float:
    """float(value), as Flask did; a failure keeps Flask's "Invalid weight value: ..." message."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise request_error(f"Invalid weight value: {exc}") from exc


class TemplateCreate(BaseModel):
    name: str | None = None  # required; checked in the route to keep "name is required"
    description: str | None = ""
    semantic_weight: float = 0.40
    skill_weight: float = 0.30
    experience_weight: float = 0.15
    education_weight: float = 0.15
    is_default: bool = False

    _weights = field_validator(*WEIGHTS, mode="before")(_weight)


class TemplateUpdate(BaseModel):
    """Only the fields sent are changed."""
    name: str | None = None
    description: str | None = None
    semantic_weight: float | None = None
    skill_weight: float | None = None
    experience_weight: float | None = None
    education_weight: float | None = None

    _weights = field_validator(*WEIGHTS, mode="before")(_weight)

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, value: Any) -> Any:
        if value is None:
            raise request_error("name is required")
        return value


class TemplateOut(BaseModel):
    id: int
    name: str
    description: str | None
    semantic_weight: float | None
    skill_weight: float | None
    experience_weight: float | None
    education_weight: float | None
    is_default: bool | None
    created_at: str | None
