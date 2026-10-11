"""Helpers shared by the routers: sessions, uploads, indexing and request-body parsing."""
import json
import logging
import os
import re
import unicodedata
import uuid
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Annotated, Any, TypeVar

from fastapi import Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.db import get_session

logger = logging.getLogger(__name__)
M = TypeVar("M", bound=BaseModel)

DbSession = Annotated[Session, Depends(get_session)]

# <32 hex chars>_<name> today; <YYYYmmdd_HHMMSS>_<name> for files stored by older versions.
_STORED_NAME = re.compile(r"^(?:[0-9a-f]{32}|\d{8}_\d{6})_(.+)$")
_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


def upload_dir(request: Request) -> Path:
    return Path(request.app.state.upload_folder)


UploadDir = Annotated[Path, Depends(upload_dir)]


def secure_filename(name: str) -> str:
    """Werkzeug's secure_filename, without the dependency: ASCII only, no path parts."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    for sep in (os.sep, os.path.altsep):
        if sep:
            name = name.replace(sep, " ")
    name = str(_UNSAFE.sub("", "_".join(name.split()))).strip("._")
    return name


def storage_name(original_name: str) -> str:
    """Unique on-disk name for an upload: <uuid4 hex>_<sanitized original name><extension>."""
    path = Path(original_name.replace("\\", "/"))
    stem = secure_filename(path.stem) or "resume"
    return f"{uuid.uuid4().hex}_{stem}{path.suffix.lower()}"


def download_name(stored_name: str) -> str:
    """The name a stored file is downloaded as: its sanitized original name."""
    match = _STORED_NAME.match(stored_name)
    return match.group(1) if match else stored_name


def remove_upload(folder: Path, stored_name: str) -> None:
    """Delete an uploaded file; a missing file is fine, other errors are logged, not raised."""
    try:
        os.remove(folder / stored_name)
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Could not delete uploaded file %s", stored_name)


def index_safely(session: Session, index: Callable[[Session, Any], Any], record: Any, what: str) -> None:
    """Chunk and embed a committed record. A failure is logged, never raised; --reindex fills the gap."""
    try:
        index(session, record)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Indexing failed for %s; run `python -m indexing --reindex` to retry", what)


def is_json(request: Request) -> bool:
    mimetype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    return mimetype == "application/json" or (mimetype.startswith("application/") and mimetype.endswith("+json"))


def require_json(request: Request) -> None:
    """Routes that read Flask's `request.json`: any other Content-Type is a 415."""
    if not is_json(request):
        raise HTTPException(415, "Did not attempt to load JSON data because the request Content-Type was not "
                                 "'application/json'.")


JsonRequired = Annotated[None, Depends(require_json)]


async def json_object(request: Request) -> dict[str, Any]:
    """Flask's get_json(silent=True) or {}: a JSON object body, else {}."""
    data: Any = None
    if is_json(request):
        try:
            data = json.loads(await request.body() or b"null")
        except ValueError:
            data = None
    return data if isinstance(data, dict) else {}


def lenient_body(model: type[M]) -> Callable[[Request], Coroutine[Any, Any, M]]:
    """A dependency for an optional JSON body: non-JSON or non-object bodies read as {}."""
    async def dependency(request: Request) -> M:
        data = await json_object(request)
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            errors = [{**e, "loc": ("body", *e["loc"])} for e in exc.errors(include_url=False)]
            raise RequestValidationError(errors, body=data) from None
    return dependency


def optional_int(value: str | None) -> int | None:
    """A lenient integer query parameter: anything unparsable is ignored, as in Flask."""
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None
