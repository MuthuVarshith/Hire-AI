"""Dashboard analytics: /api/analytics/* (recruiter). Bodies are AnalyticsService's, unchanged."""
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from analytics_service import AnalyticsService
from app.auth import Recruiter
from app.routers._shared import DbSession, optional_int
from models import Job

router = APIRouter(tags=["analytics"])


class DashboardOut(BaseModel):
    total_screened: int
    shortlisted: int
    in_interview: int
    offers: int
    hired: int
    rejected: int
    average_score: float
    score_distribution: dict[str, int]
    pipeline_stages: dict[str, int]
    candidates_by_job: dict[str, int]
    skill_gaps: dict[str, int]
    top_matched_skills: dict[str, int]
    shortlist_rate: float


class TopCandidateOut(BaseModel):
    id: int
    name: str
    email: str | None
    score: float
    status: str | None


@router.get("/api/analytics/dashboard", response_model=DashboardOut)
def get_dashboard(user: Recruiter, session: DbSession, job_id: str | None = None) -> dict[str, Any]:
    """An unparsable job_id is ignored, as in Flask."""
    return AnalyticsService(session).get_dashboard_metrics(optional_int(job_id))


@router.get("/api/analytics/jobs/{job_id:int}")
def get_job_analytics(job_id: int, user: Recruiter, session: DbSession) -> dict[str, Any]:
    if session.get(Job, job_id) is None:
        raise HTTPException(404, "Job not found")
    return AnalyticsService(session).get_job_metrics(job_id)


@router.get("/api/analytics/top-candidates", response_model=list[TopCandidateOut])
def get_top_candidates(user: Recruiter, session: DbSession, job_id: str | None = None,
                       limit: Annotated[int, Query(ge=0)] = 10) -> list[dict[str, Any]]:
    return AnalyticsService(session).get_top_candidates(optional_int(job_id), limit)
