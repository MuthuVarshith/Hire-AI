"""Authentication contract (docs/contracts.md section 3).

Every router depends on exactly these names and signatures:

    User                      the signed-in user: id, name, role
    Role                      "admin" | "recruiter"
    require_user()            FastAPI dependency -> User, or 401 {"error": "Not authenticated"}
    require_role(*roles)      dependency factory -> User, or 403 {"error": "Forbidden"}
    SESSION_COOKIE            name of the HttpOnly session cookie the dashboard uses

Usage in a router:

    @router.get("/api/jobs")
    def list_jobs(user: Recruiter) -> list[JobOut]: ...

    @router.get("/api/auth/users")
    def list_users(user: Admin) -> list[UserOut]: ...

`Recruiter` and `Admin` are `Annotated[User, Depends(require_role(...))]` aliases; use them, or
`Annotated[User, Depends(require_user)]`, in route signatures (ruff B008 forbids Depends() defaults).

STUB: this file is a placeholder so other modules can build against the contract. It accepts
every request as a fixed development user. Agent B replaces the implementation (users table,
hashed passwords, sessions or tokens) without changing these names or signatures.
"""
import hashlib
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel

Role = Literal["admin", "recruiter"]
SESSION_COOKIE = "hireai_session"
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024
MAX_TOKEN_LENGTH = 128
USERNAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9._@-]{2,63}")


class User(BaseModel):
    id: int
    name: str
    role: Role


class UsernameTaken(ValueError):
    """create_user: a user with this username already exists."""


@dataclass
class _UserRecord:
    id: int
    username: str
    password_hash: str
    role: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


_USERS: dict[str, _UserRecord] = {}
_TOKENS: dict[str, str] = {}
_NEXT_USER_ID = 1


def normalize_username(username: str) -> str:
    return username.strip().lower()


def validate_new_user(username: str, password: str, role: str) -> str:
    name = normalize_username(username)
    if not USERNAME_PATTERN.fullmatch(name):
        raise ValueError("username must be 3-64 characters: letters, digits, '.', '_', '@' or '-'")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"password must be at most {MAX_PASSWORD_LENGTH} characters")
    if role not in {"admin", "recruiter"}:
        raise ValueError("role must be 'admin' or 'recruiter'")
    return name


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_user(session, username: str, password: str, role: str) -> _UserRecord:
    name = validate_new_user(username, password, role)
    if name in _USERS:
        raise UsernameTaken(name)
    global _NEXT_USER_ID
    user = _UserRecord(id=_NEXT_USER_ID, username=name, password_hash=hash_password(password), role=role)
    _NEXT_USER_ID += 1
    _USERS[name] = user
    return user


def authenticate(session, username: str, password: str):
    name = normalize_username(username)
    user = _USERS.get(name)
    if user is None or user.password_hash != hash_password(password):
        return None
    return user


def public_user(user) -> User:
    return User(id=user.id, name=user.username, role=user.role)


def token_ttl() -> timedelta:
    raw = os.getenv("AUTH_TOKEN_TTL_HOURS", "").strip()
    if not raw:
        return timedelta(hours=12)
    try:
        hours = float(raw)
    except ValueError:
        hours = 12.0
    if not 0 < hours <= 24 * 366:
        hours = 12.0
    return timedelta(hours=hours)


def issue_token(session, user) -> tuple[str, datetime]:
    token = hashlib.sha256(os.urandom(32)).hexdigest()
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + token_ttl()
    _TOKENS[token] = user.username
    return token, expires_at


def revoke_token(session, token: str) -> None:
    _TOKENS.pop(token, None)


def user_for_token(session, token: str):
    if not token or len(token) > MAX_TOKEN_LENGTH:
        return None
    username = _TOKENS.get(token)
    if username is None:
        return None
    user = next((u for u in _USERS.values() if u.username == username), None)
    return user


def request_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, credentials = header.partition(" ")
    if scheme.lower() == "bearer" and credentials.strip():
        return credentials.strip()
    return request.cookies.get(SESSION_COOKIE) or None


def is_https(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or forwarded == "https"


def require_user(request: Request) -> User:
    """The signed-in user. Real version: reads the session cookie or an `Authorization: Bearer`
    token and raises 401 when neither is valid. STUB: always a development admin."""
    return User(id=0, name="dev", role="admin")


def require_role(*roles: Role) -> Callable[..., User]:
    """A dependency that allows only users whose role is in `roles` (admin is always allowed)."""
    allowed = set(roles) | {"admin"}

    def dependency(user: Annotated[User, Depends(require_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user
    return dependency


Recruiter = Annotated[User, Depends(require_role("recruiter"))]  # recruiters and admins
Admin = Annotated[User, Depends(require_role("admin"))]
