"""POST /api/ask models (docs/contracts.md section 5, "Ask result")."""
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import request_error


class AskRequest(BaseModel):
    """Same checks and messages as the Flask route; ask.answer_question validates length."""
    question: str = Field(default=None, validate_default=True)
    job_id: int | None = None

    @field_validator("question", mode="before")
    @classmethod
    def _question(cls, value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            raise request_error("question is required")
        return value

    @field_validator("job_id", mode="before")
    @classmethod
    def _job_id(cls, value: Any) -> Any:
        # bool is a subclass of int, so {"job_id": true} would otherwise be read as job 1.
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise request_error("job_id must be an integer")
        return value


class CitationOut(BaseModel):
    number: int
    candidate_id: int
    candidate_name: str
    section: str
    text: str
    char_start: int
    char_end: int
    similarity: float


class AskResult(BaseModel):
    question: str
    found: bool
    answer: str
    citations: list[CitationOut]
    generated: bool
    top_similarity: float | None
    summary_unavailable: bool
    summary_unavailable_reason: str | None
