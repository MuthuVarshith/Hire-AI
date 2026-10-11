"""POST /api/ask (recruiter): answer from resume chunks only, citing the passages used.

The 16 KiB body limit is applied by app.main.BodySizeLimit before the body is read.
"""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

import ask
import config as cfg
import embeddings
from app.auth import Recruiter
from app.routers._shared import DbSession, lenient_body
from app.schemas.ask import AskRequest, AskResult
from models import Job

router = APIRouter(tags=["ask"])
ASK_MAX_BODY_BYTES = 16 * 1024  # enforced in app.main (SMALL_BODY_BYTES)


@router.post("/api/ask", response_model=AskResult)
def ask_candidate_pool(user: Recruiter, session: DbSession,
                       body: Annotated[AskRequest, Depends(lenient_body(AskRequest))]) -> dict[str, Any]:
    if body.job_id is not None and session.get(Job, body.job_id) is None:
        raise HTTPException(404, "Job not found")
    try:
        result = ask.answer_question(session, body.question, embeddings.get_provider(), job_id=body.job_id,
                                     api_key=cfg.get_api_key())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return result.to_dict()
