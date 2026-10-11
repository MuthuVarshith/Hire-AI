"""Candidates: /api/candidates (recruiter)."""
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.datastructures import FormData, UploadFile

import duplicate_detection
import indexing
import resume_parser
from app.auth import Recruiter
from app.routers._shared import (DbSession, UploadDir, download_name, index_safely, lenient_body, optional_int,
                                 remove_upload, storage_name)
from app.schemas.candidates import (CandidateDetailOut, CandidateOut, CandidateUpdate, CandidateWithScreeningOut)
from app.schemas.common import MessageOut
from models import Candidate, Job, PipelineStatus, ScreeningResult

logger = logging.getLogger(__name__)
router = APIRouter(tags=["candidates"])
ALLOWED_RESUME_EXTENSIONS = set(os.getenv("ALLOWED_RESUME_EXTENSIONS", ".txt,.pdf,.docx").split(","))


async def _form(request: Request) -> AsyncIterator[FormData]:
    """The multipart form, read here so the job_id form field and the file reach a sync route."""
    form = await request.form()
    try:
        yield form
    finally:
        await form.close()


Form = Annotated[FormData, Depends(_form)]


def with_screening(candidate: Candidate) -> dict[str, Any]:
    data = candidate.to_dict(include_screening=True)
    data["screening"] = data.get("latest_screening")
    return data


def _candidate_or_404(session: DbSession, candidate_id: int) -> Candidate:
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(404, "Candidate not found")
    return candidate


@router.post("/api/candidates", status_code=201, response_model=CandidateOut,
             responses={409: {"description": "Duplicate candidate"}})
def upload_candidate(user: Recruiter, form: Form, session: DbSession, uploads: UploadDir,
                     job_id: str | None = None) -> Any:
    raw_job_id = job_id or form.get("job_id")
    if not raw_job_id or not isinstance(raw_job_id, str):
        raise HTTPException(400, "job_id is required")
    try:
        job_number = int(raw_job_id)
    except ValueError:
        raise HTTPException(400, "job_id must be an integer") from None
    if session.get(Job, job_number) is None:
        raise HTTPException(404, f"Job {job_number} not found")

    if "resume" not in form:
        raise HTTPException(400, "resume file is required")
    file = form["resume"]
    if not isinstance(file, UploadFile) or not file.filename:
        raise HTTPException(400, "No resume file provided")
    extension = Path(file.filename).suffix.lower()
    if extension not in ALLOWED_RESUME_EXTENSIONS:
        raise HTTPException(400, f"File type {extension} not allowed")

    filename = storage_name(file.filename)
    filepath = uploads / filename
    with open(filepath, "wb") as out:
        while chunk := file.file.read(1024 * 1024):
            out.write(chunk)
    profile = resume_parser.parse_resume(str(filepath))

    is_dup, existing = duplicate_detection.is_potential_duplicate(
        session, email=profile.email, phone=profile.phone, name=profile.name, job_id=job_number)
    if is_dup and existing:
        remove_upload(uploads, filename)
        return JSONResponse(status_code=409, content={
            "error": "Duplicate candidate detected",
            "existing_candidate": {"id": existing.id, "name": existing.name, "email": existing.email,
                                   "status": existing.status.value if existing.status else None}})

    candidate = Candidate(name=profile.name, email=profile.email, phone=profile.phone, resume_filename=filename,
                          resume_text=profile.raw_text, skills=profile.skills,
                          experience_years=profile.experience_years, education=profile.education,
                          work_history=profile.work_history, job_id=job_number, status=PipelineStatus.SCREENED)
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    index_safely(session, indexing.index_candidate, candidate, f"candidate {candidate.id}")
    logger.info("Created candidate %s: %s", candidate.id, candidate.name)
    return candidate.to_dict(include_screening=False)


@router.get("/api/candidates", response_model=list[CandidateWithScreeningOut], response_model_exclude_unset=True)
def list_candidates(user: Recruiter, session: DbSession, job_id: str | None = None, status: str | None = None,
                    sort_by: str = "created_at") -> list[dict[str, Any]]:
    """Invalid job_id or status filters are ignored, as in Flask."""
    query = session.query(Candidate)
    job_number = optional_int(job_id)
    if job_number is not None:
        query = query.filter(Candidate.job_id == job_number)
    if status and status.upper() in PipelineStatus.__members__:
        query = query.filter(Candidate.status == PipelineStatus[status.upper()])
    rows = [with_screening(c) for c in query.order_by(Candidate.created_at.desc(), Candidate.id.desc()).all()]
    if sort_by == "score":
        # Highest latest score first; unscored candidates last, newest first (the sort is stable).
        rows.sort(key=lambda c: (c["screening"] is None, -(c["screening"] or {}).get("composite_score", 0.0)))
    return rows


@router.get("/api/candidates/{candidate_id:int}", response_model=CandidateDetailOut,
            response_model_exclude_unset=True)
def get_candidate(candidate_id: int, user: Recruiter, session: DbSession) -> dict[str, Any]:
    data = with_screening(_candidate_or_404(session, candidate_id))
    history = (session.query(ScreeningResult).filter(ScreeningResult.candidate_id == candidate_id)
               .order_by(ScreeningResult.id).all())
    data["screening_history"] = [s.to_dict() for s in history]
    return data


@router.put("/api/candidates/{candidate_id:int}", response_model=CandidateOut)
def update_candidate(candidate_id: int, user: Recruiter, session: DbSession,
                     body: Annotated[CandidateUpdate, Depends(lenient_body(CandidateUpdate))]) -> dict[str, Any]:
    """The body is optional: a non-JSON body changes nothing."""
    candidate = _candidate_or_404(session, candidate_id)
    if "status" in body.model_fields_set:
        if body.status is None or body.status.upper() not in PipelineStatus.__members__:
            raise HTTPException(400, f"Invalid status: {body.status}")
        candidate.status = PipelineStatus[body.status.upper()]
    if "notes" in body.model_fields_set:
        candidate.notes = body.notes
    session.commit()
    logger.info("Updated candidate %s", candidate_id)
    return candidate.to_dict()


@router.get("/api/candidates/{candidate_id:int}/resume", response_class=FileResponse)
def download_resume(candidate_id: int, user: Recruiter, session: DbSession, uploads: UploadDir) -> FileResponse:
    candidate = session.get(Candidate, candidate_id)
    if candidate is None or not candidate.resume_filename:
        raise HTTPException(404, "Resume not found")
    filepath = uploads / candidate.resume_filename
    if not filepath.is_file():
        raise HTTPException(404, "Resume file not found on disk")
    return FileResponse(filepath, filename=download_name(candidate.resume_filename))


@router.delete("/api/candidates/{candidate_id:int}", response_model=MessageOut)
def delete_candidate(candidate_id: int, user: Recruiter, session: DbSession, uploads: UploadDir) -> dict[str, str]:
    candidate = _candidate_or_404(session, candidate_id)
    if candidate.resume_filename:
        remove_upload(uploads, candidate.resume_filename)
    session.delete(candidate)
    session.commit()
    logger.info("Deleted candidate %s", candidate_id)
    return {"message": "Candidate deleted"}
