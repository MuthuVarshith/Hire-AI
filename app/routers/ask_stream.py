"""POST /api/ask/stream: the streaming chat endpoint (docs/contracts.md section 4).

Validation matches POST /api/ask and is answered as ordinary JSON before the stream starts. The
event stream opens its own database session and closes it when the stream ends: a yield-dependency
session may already be closed while a StreamingResponse is still being sent.
"""
import json
import logging
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response, StreamingResponse

import ask
import config
import embeddings
from app import ask_stream
from app import db as app_db
from app.auth import Recruiter
from models import Job

logger = logging.getLogger(__name__)
router = APIRouter()

ASK_MAX_BODY_BYTES = 16 * 1024  # a 500-character question plus job_id fits easily


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def _read_body(request: Request, limit: int) -> bytes | None:
    """The body, or None when it is larger than `limit` (checked as it arrives, not only by Content-Length)."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        return None
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            return None
    return body


def _json_object(request: Request, raw: bytes) -> dict[str, Any]:
    """Like Flask's get_json(silent=True): a non-JSON content type or body reads as {}."""
    mimetype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if not (mimetype == "application/json" or (mimetype.startswith("application/") and mimetype.endswith("+json"))):
        return {}
    try:
        body = json.loads(raw)
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _job_exists(job_id: int) -> bool:
    session = app_db.SessionLocal()
    try:
        return session.get(Job, job_id) is not None
    finally:
        session.close()


def _events(question: str, job_id: int | None) -> Iterator[str]:
    """Runs in Starlette's threadpool, so blocking retrieval and LLM calls don't stall the event loop."""
    session = app_db.SessionLocal()
    try:
        try:
            provider = embeddings.get_provider()
            api_key = config.get_api_key()
        except Exception:
            logger.exception("Could not start the answer stream")
            yield ask_stream.internal_error()
            return
        yield from ask_stream.stream_answer(session, question, provider, job_id=job_id, api_key=api_key)
    finally:
        session.close()


@router.post("/api/ask/stream", response_model=None)
async def ask_stream_route(request: Request, user: Recruiter) -> Response:
    raw = await _read_body(request, ASK_MAX_BODY_BYTES)
    if raw is None:
        return _error(413, "request body is too large")
    body = _json_object(request, raw)
    question, job_id = body.get("question"), body.get("job_id")
    if not isinstance(question, str) or not question.strip():
        return _error(400, "question is required")
    if job_id is not None and (isinstance(job_id, bool) or not isinstance(job_id, int)):
        return _error(400, "job_id must be an integer")
    if job_id is not None and not await run_in_threadpool(_job_exists, job_id):
        return _error(404, "Job not found")
    try:
        question, job_id = ask.validate_input(question, job_id)
    except ValueError as exc:
        return _error(400, str(exc))
    return StreamingResponse(ask_stream.with_keepalive(_events(question, job_id)), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
