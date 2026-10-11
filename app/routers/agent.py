"""The recruiting agent: POST /api/agent/run and POST /api/agent/approve/{thread_id} (recruiter).

Both accept only application/json (400 otherwise, as before) and at most 16 KiB (app.main).
"""
from collections.abc import Callable, Coroutine
from typing import Annotated, Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import agent_api
import embeddings
from app.auth import Recruiter
from app.routers._shared import DbSession, lenient_body
from app.schemas.agent import AgentRunOut, AgentRunRequest, ApproveRequest

router = APIRouter(tags=["agent"])
M = TypeVar("M", bound=BaseModel)


def _json_only(model: type[M]) -> Callable[[Request], Coroutine[Any, Any, M]]:
    parse = lenient_body(model)

    async def dependency(request: Request) -> M:
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPException(400, "Content-Type must be application/json")
        return await parse(request)
    return dependency


def _respond(result: agent_api.Response) -> dict[str, Any]:
    body, status = result
    if status != 200:
        raise HTTPException(status, body["error"])
    return body


@router.post("/api/agent/run", response_model=AgentRunOut)
def agent_run(user: Recruiter, session: DbSession,
              body: Annotated[AgentRunRequest, Depends(_json_only(AgentRunRequest))]) -> dict[str, Any]:
    """Run the agent. A proposed shortlist comes back as "pending_approval" with a thread_id."""
    return _respond(agent_api.run(body.request, body.job_id, session, embeddings.get_provider,
                                  agent_api.agent_checkpointer))


@router.post("/api/agent/approve/{thread_id}", response_model=AgentRunOut)
def agent_approve(thread_id: str, user: Recruiter, session: DbSession,
                  body: Annotated[ApproveRequest, Depends(_json_only(ApproveRequest))]) -> dict[str, Any]:
    """Approve or reject a proposed shortlist as the signed-in user; the agent itself cannot approve."""
    decision = {"decision": body.decision, "note": body.note, "reviewer": user.name, "reviewer_id": user.id}
    return _respond(agent_api.decide(thread_id, decision, session, agent_api.agent_checkpointer))
