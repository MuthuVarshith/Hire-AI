"""Candidate and Screening models (docs/contracts.md section 5)."""
from typing import Any

from pydantic import BaseModel


class ScreeningOut(BaseModel):
    id: int
    candidate_id: int
    job_id: int
    composite_score: float
    semantic_score: float
    skill_match_score: float
    experience_score: float
    education_score: float
    matched_skills: list[str]
    missing_skills: list[str]
    matched_preferred_skills: list[str]
    reasoning: str | None
    strengths: list[str]
    skill_gaps: list[str]
    created_at: str | None


class CandidateOut(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    resume_filename: str | None
    skills: list[str]
    experience_years: float | None
    education: list[dict[str, Any]]
    work_history: list[dict[str, Any]]
    status: str | None
    created_at: str | None
    notes: str | None
    job_id: int | None
    job_title: str | None


class CandidateWithScreeningOut(CandidateOut):
    screening: ScreeningOut | None  # contract name: the latest screening, or null
    latest_screening: ScreeningOut | None = None  # Flask's name, present only when screened (left unset otherwise)


class CandidateDetailOut(CandidateWithScreeningOut):
    screening_history: list[ScreeningOut]


class CandidateUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None


class DuplicateCandidate(BaseModel):
    id: int
    name: str
    email: str | None
    status: str | None
