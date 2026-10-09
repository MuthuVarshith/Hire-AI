"""Request handling for POST /api/agent/run and POST /api/agent/approve/<thread_id>.

Kept out of app.py, which predates strict typing, so this code is type-checked. app.py's routes
call run() and decide() and turn any unexpected exception into its generic 500.

Cross-site protection: app.py serves /api/agent/* without CORS headers (same origin only), and
both endpoints accept only application/json bodies, which a cross-site HTML form can't send
without a CORS preflight. There is no authentication yet, so `reviewer` is self-declared.
"""
import logging
import re
from collections.abc import Callable
from typing import Any

from flask import Request
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import ValidationError
from sqlalchemy.orm import Session

import agent
import agent_llm
from agent_tools import MAX_ID, ToolContext
from embeddings import EmbeddingProvider
from models import Job

logger = logging.getLogger(__name__)

Response = tuple[dict[str, Any], int]
MAX_BODY_BYTES = 16 * 1024
NOT_WAITING = "No run is waiting for approval with this thread_id"
_THREAD_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _body(request: Request) -> dict[str, Any] | Response:
    """The JSON object body ({} for a non-object), or an error response."""
    if request.content_length is not None and request.content_length > MAX_BODY_BYTES:
        return {"error": "request body is too large"}, 413
    if request.mimetype != "application/json":
        return {"error": "Content-Type must be application/json"}, 400
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def run(request: Request, sessions: Callable[[], Session], embedding_provider: Callable[[], EmbeddingProvider],
        checkpointer: Callable[[], BaseCheckpointSaver[Any]]) -> Response:
    """Run the agent; the result has status "pending_approval" and a thread_id when it proposes a shortlist."""
    body = _body(request)
    if isinstance(body, tuple):
        return body
    job_id = body.get("job_id")
    try:
        text = agent.validate_request(body.get("request"), job_id)
    except ValueError as exc:
        return {"error": str(exc)}, 400
    if job_id is not None and not 1 <= job_id <= MAX_ID:  # no such row can exist
        return {"error": "Job not found"}, 404
    try:
        planner = agent.make_planner(agent_llm.get_provider())
    except agent_llm.ProviderError:
        logger.exception("Agent LLM provider is misconfigured")
        return {"error": "The agent's LLM provider is not available"}, 503
    session = sessions()
    try:
        if job_id is not None and session.get(Job, job_id) is None:
            return {"error": "Job not found"}, 404
        ctx = ToolContext(session=session, provider=embedding_provider())
        return agent.start_run(ctx, text, planner, checkpointer(), job_id=job_id), 200
    finally:
        session.close()


def decide(request: Request, thread_id: str, sessions: Callable[[], Session],
           checkpointer: Callable[[], BaseCheckpointSaver[Any]]) -> Response:
    """Record a recruiter's approve or reject and resume the paused run. The only way a shortlist is saved."""
    body = _body(request)
    if isinstance(body, tuple):
        return body
    decision = {"decision": body.get("decision"), "reviewer": body.get("reviewer"), "note": body.get("note")}
    try:
        agent.Decision.model_validate(decision)
    except ValidationError:
        return {"error": "decision must be 'approve' or 'reject', reviewer is required, and note must be text"}, 400
    if not _THREAD_ID.fullmatch(thread_id):
        return {"error": NOT_WAITING}, 404
    saver = checkpointer()
    session = sessions()
    try:
        result = agent.resume_run(ToolContext(session=session, provider=None), thread_id, decision,
                                  agent.rule_based_planner, saver)
    except agent.AlreadyDecided:
        return {"error": "This run was already decided"}, 409
    except agent.RunNotPending:
        return {"error": NOT_WAITING}, 404
    finally:
        session.close()
    if result["status"] in ("job_deleted", "candidates_deleted"):
        return {"error": result["message"]}, 410
    return result, 200
