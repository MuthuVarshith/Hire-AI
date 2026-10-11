"""The Hire AI FastAPI application (docs/contracts.md sections 1 and 2).

Run with `uvicorn app.main:app --host 127.0.0.1 --port 8000`.
"""
import logging
import os
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.routers import (agent, analytics, ask, ask_stream, auth, candidates, health, jobs, scoring,
                         templates)
from app.schemas.common import REQUEST_ERROR

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
MAX_CONTENT_LENGTH = int(os.getenv("MAX_RESUME_SIZE_MB", "10")) * 1024 * 1024
SMALL_BODY_BYTES = 16 * 1024  # /api/ask and /api/agent/*: a question or request plus job_id fits easily
TOO_LARGE = "The data value transmitted exceeds the capacity limit."
SMALL_TOO_LARGE = "request body is too large"
GENERIC = {400: "Bad request", 404: "Not found", 405: "Method not allowed", 500: "Internal server error"}


def body_limit(path: str) -> tuple[int, str]:
    if path == "/api/ask" or path.startswith(("/api/ask/", "/api/agent/")):
        return SMALL_BODY_BYTES, SMALL_TOO_LARGE
    return MAX_CONTENT_LENGTH, TOO_LARGE


class BodySizeLimit:
    """413 for bodies over the limit: by Content-Length up front, or while a chunked body streams."""

    def __init__(self, app: ASGIApp, limit: Callable[[str], tuple[int, str]] = body_limit) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        max_bytes, message = self.limit(scope["path"])
        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > max_bytes:
            await JSONResponse({"error": message}, status_code=413)(scope, receive, send)
            return
        received = 0

        async def limited() -> Message:
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > max_bytes:
                    raise StarletteHTTPException(413, message)
            return msg
        await self.app(scope, limited, send)


class UnhandledErrors:
    """Any unexpected exception: details to the log (logger.exception), a generic 500 to the client.

    A middleware rather than an Exception handler, so the error is not re-raised to the server
    (no double logging) and TestClient gets the 500 response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking(msg: Message) -> None:
            nonlocal started
            started = started or msg["type"] == "http.response.start"
            await send(msg)
        try:
            await self.app(scope, receive, tracking)
        except Exception:
            logger.exception("Unexpected error on %s %s", scope.get("method"), scope.get("path"))
            if started:
                raise
            await JSONResponse({"error": GENERIC[500]}, status_code=500)(scope, receive, send)


def validation_message(errors: list[Any]) -> str:
    first = errors[0] if errors else {}
    if first.get("type") == REQUEST_ERROR:
        return str(first.get("msg"))
    if first.get("type") == "json_invalid":
        return "Request body is not valid JSON"
    field = ".".join(str(p) for p in first.get("loc", ()) if p not in ("body", "query", "path", "header", "cookie"))
    msg = str(first.get("msg", "Invalid request"))
    return f"{field}: {msg}" if field else msg


async def http_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)
    detail: Any = exc.detail
    if isinstance(detail, dict):
        content = detail
    elif isinstance(detail, str) and detail != HTTPStatus(exc.status_code).phrase:
        content = {"error": detail}
    else:
        content = {"error": GENERIC.get(exc.status_code, HTTPStatus(exc.status_code).phrase)}
    return JSONResponse(content, status_code=exc.status_code, headers=exc.headers)


async def validation_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)
    return JSONResponse({"error": validation_message(list(exc.errors()))}, status_code=400)


DEFAULT_AGENT_CHECKPOINT_DB = os.path.join(BASE_DIR, "agent_checkpoints.db")
app = FastAPI(title="Hire AI", version="2.0.0")
app.state.upload_folder = os.getenv("UPLOAD_FOLDER", "uploads")
os.makedirs(app.state.upload_folder, exist_ok=True)
app.add_exception_handler(StarletteHTTPException, http_error)
app.add_exception_handler(RequestValidationError, validation_error)
app.add_middleware(BodySizeLimit)
app.add_middleware(UnhandledErrors)
# No CORS middleware: the dashboard is same-origin.

for _router in (health.router, auth.router, jobs.router, candidates.router, scoring.router, templates.router,
                analytics.router, ask.router, ask_stream.router, agent.router):
    app.include_router(_router)

if (BASE_DIR / "static").is_dir():  # created by agent C
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def _page(name: str) -> Response:
    path = BASE_DIR / "templates" / name
    if not path.is_file():
        return JSONResponse({"error": GENERIC[404]}, status_code=404)
    return FileResponse(path)


@app.get("/", include_in_schema=False)
def index_page() -> Response:
    return _page("index.html")


@app.get("/login", include_in_schema=False)
def login_page() -> Response:
    return _page("login.html")
