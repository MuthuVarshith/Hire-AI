"""Agent run and approval models (docs/contracts.md sections 3 and 5, "Agent run")."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidatorFunctionWrapHandler, model_validator

from app.schemas.common import request_error

APPROVE_ERROR = "decision must be 'approve' or 'reject', and note must be text"


class AgentRunRequest(BaseModel):
    """Types are checked by agent.validate_request, so its messages reach the client unchanged."""
    request: Any = None
    job_id: Any = None


class ApproveRequest(BaseModel):
    """The reviewer is the signed-in user; a `reviewer` field in the body is ignored."""
    model_config = ConfigDict(strict=True, extra="ignore")
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="wrap")
    @classmethod
    def _one_message(cls, data: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        try:
            return handler(data)
        except ValidationError:
            raise request_error(APPROVE_ERROR) from None


class AgentRunOut(BaseModel):
    thread_id: str
    status: Literal["running", "pending_approval", "answered", "stopped", "approved", "rejected", "job_deleted",
                    "candidates_deleted", "error"]
    message: str
    steps: list[dict[str, Any]]
    proposal: dict[str, Any] | None
    decision: dict[str, Any] | None
    shortlist: dict[str, Any] | None
