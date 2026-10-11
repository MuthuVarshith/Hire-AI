"""Job postings: /api/jobs (recruiter)."""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

import config as cfg
import indexing
import jd_parser
from app.auth import Recruiter
from app.routers._shared import DbSession, JsonRequired, UploadDir, index_safely, remove_upload
from app.schemas.common import MessageOut
from app.schemas.jobs import JobCreate, JobOut, JobUpdate
from models import Job

logger = logging.getLogger(__name__)
router = APIRouter(tags=["jobs"])


def _job_or_404(session: DbSession, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/api/jobs", status_code=201, response_model=JobOut)
def create_job(user: Recruiter, _json: JsonRequired, body: JobCreate, session: DbSession) -> dict[str, Any]:
    if not body.title:
        raise HTTPException(400, "title is required")
    if not body.description_text:
        raise HTTPException(400, "description_text is required")
    jd = jd_parser.parse_jd_text(body.description_text, cfg.get_api_key())
    job = Job(title=body.title or jd.title, description_text=body.description_text,
              required_skills=jd.required_skills, preferred_skills=jd.preferred_skills,
              min_experience_years=jd.min_experience_years, required_education=jd.required_education,
              responsibilities=jd.responsibilities, scoring_template_id=body.scoring_template_id)
    session.add(job)
    session.commit()
    session.refresh(job)
    index_safely(session, indexing.index_job, job, f"job {job.id}")
    logger.info("Created job %s: %s", job.id, job.title)
    return job.to_dict()


@router.get("/api/jobs", response_model=list[JobOut])
def list_jobs(user: Recruiter, session: DbSession) -> list[dict[str, Any]]:
    return [job.to_dict() for job in session.query(Job).order_by(Job.created_at.desc()).all()]


@router.get("/api/jobs/{job_id:int}", response_model=JobOut)
def get_job(job_id: int, user: Recruiter, session: DbSession) -> dict[str, Any]:
    return _job_or_404(session, job_id).to_dict()


@router.put("/api/jobs/{job_id:int}", response_model=JobOut)
def update_job(job_id: int, user: Recruiter, _json: JsonRequired, body: JobUpdate,
               session: DbSession) -> dict[str, Any]:
    job = _job_or_404(session, job_id)
    if body.title is not None:
        job.title = body.title
    description_changed = body.description_text is not None and body.description_text != job.description_text
    if body.description_text is not None:
        job.description_text = body.description_text
    if "scoring_template_id" in body.model_fields_set:
        job.scoring_template_id = body.scoring_template_id
    session.commit()
    if description_changed:
        index_safely(session, indexing.index_job, job, f"job {job_id}")
    logger.info("Updated job %s", job_id)
    return job.to_dict()


@router.delete("/api/jobs/{job_id:int}", response_model=MessageOut)
def delete_job(job_id: int, user: Recruiter, session: DbSession, uploads: UploadDir) -> dict[str, str]:
    job = _job_or_404(session, job_id)
    resume_files = [c.resume_filename for c in job.candidates if c.resume_filename]
    session.delete(job)
    session.commit()
    # Only after the commit: if the delete fails, candidates still exist and need their files.
    for name in resume_files:
        remove_upload(uploads, name)
    logger.info("Deleted job %s and %s resume file(s)", job_id, len(resume_files))
    return {"message": "Job deleted"}
