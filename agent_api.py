"""Framework-neutral logic for POST /api/agent/run and POST /api/agent/approve/{thread_id}.

app/routers/agent.py parses and validates the request (JSON only, 16 KiB, signed-in user) and turns
the (body, status) these functions return into the response. The reviewer is the signed-in user.
"""
import logging
import os
import re
import threading
from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
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

# Default: agent_checkpoints.db in the repository root, which .gitignore's *.db rule keeps out of git.
DEFAULT_AGENT_CHECKPOINT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_checkpoints.db")
_agent_checkpointer: BaseCheckpointSaver[Any] | None = None
_agent_checkpointer_lock = threading.Lock()


def agent_checkpointer() -> BaseCheckpointSaver[Any]:
    """The agent's checkpointer: a SQLite file (AGENT_CHECKPOINT_DB), so paused runs survive a restart.
    Checkpoints hold tool results, i.e. resume passages, so the file is as sensitive as the database."""
    global _agent_checkpointer
    with _agent_checkpointer_lock:
        if _agent_checkpointer is None:
            _agent_checkpointer = agent.sqlite_checkpointer(
                os.getenv("AGENT_CHECKPOINT_DB") or DEFAULT_AGENT_CHECKPOINT_DB)
        return _agent_checkpointer


def run(request: Any, job_id: Any, session: Session, embedding_provider: Callable[[], EmbeddingProvider],
        checkpointer: Callable[[], BaseCheckpointSaver[Any]]) -> Response:
    """Run the agent; the result has status "pending_approval" and a thread_id when it proposes a shortlist."""
    try:
        text = agent.validate_request(request, job_id)
    except ValueError as exc:
        return {"error": str(exc)}, 400
    if job_id is not None and not 1 <= job_id <= MAX_ID:  # no such row can exist
        return {"error": "Job not found"}, 404
    try:
        planner = agent.make_planner(agent_llm.get_provider())
    except agent_llm.ProviderError:
        logger.exception("Agent LLM provider is misconfigured")
        return {"error": "The agent's LLM provider is not available"}, 503
    if job_id is not None and session.get(Job, job_id) is None:
        return {"error": "Job not found"}, 404
    ctx = ToolContext(session=session, provider=embedding_provider())
    return agent.start_run(ctx, text, planner, checkpointer(), job_id=job_id), 200


def decide(thread_id: str, decision: dict[str, Any], session: Session,
           checkpointer: Callable[[], BaseCheckpointSaver[Any]]) -> Response:
    """Record an approve or reject and resume the paused run. The only way a shortlist is saved.

    `decision` is {"decision", "note", "reviewer", "reviewer_id"} (docs/contracts.md section 3)."""
    if not _THREAD_ID.fullmatch(thread_id):
        return {"error": NOT_WAITING}, 404
    try:
        result = agent.resume_run(ToolContext(session=session, provider=None), thread_id, decision,
                                  agent.rule_based_planner, checkpointer())
    except agent.AlreadyDecided:
        return {"error": "This run was already decided"}, 409
    except agent.RunNotPending:
        return {"error": NOT_WAITING}, 404
    if result["status"] in ("job_deleted", "candidates_deleted"):
        return {"error": result["message"]}, 410
    return result, 200
