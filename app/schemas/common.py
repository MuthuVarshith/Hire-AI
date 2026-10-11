"""Shared response shapes and the helper that keeps Flask's explicit validation messages."""
from pydantic import BaseModel
from pydantic_core import PydanticCustomError

REQUEST_ERROR = "request_error"


def request_error(message: str) -> PydanticCustomError:
    """A validation error whose message reaches the client verbatim (see app.main's 400 handler)."""
    return PydanticCustomError(REQUEST_ERROR, "{message}", {"message": message})


class ErrorOut(BaseModel):
    error: str


class MessageOut(BaseModel):
    message: str
