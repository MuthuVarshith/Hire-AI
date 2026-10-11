"""Authentication (docs/contracts.md section 3).

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

Token design: server-side sessions. Login creates a random 256-bit token (`secrets.token_urlsafe`),
returns it once, and stores only its SHA-256 hash in the `sessions` table with an expiry of
AUTH_TOKEN_TTL_HOURS (default 12). A request is authenticated by hashing the presented token and
looking the hash up, so a database leak reveals no usable token, and logout revokes a token at once
by deleting its row; a signed JWT can't be revoked before it expires without a server-side list
anyway. The token travels in the `hireai_session` cookie (HttpOnly, SameSite=Strict, Secure over
HTTPS) or an `Authorization: Bearer` header. AUTH_SECRET is not used by this design.

Passwords are hashed with argon2id (argon2-cffi defaults), must be 12+ characters and are never
logged. There are no default users: the first admin comes from `python -m app.cli create-admin`.
"""
import hashlib
import logging
import os
import re
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from functools import cache
from typing import Annotated, Literal, cast, get_args

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from app.db import get_session

logger = logging.getLogger(__name__)

Role = Literal["admin", "recruiter"]
ROLES: tuple[Role, ...] = get_args(Role)
SESSION_COOKIE = "hireai_session"

DEFAULT_TOKEN_TTL_HOURS = 12.0
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024        # argon2 hashes any length; this only bounds the work per request
MAX_TOKEN_LENGTH = 128            # issued tokens are 43 characters
USERNAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9._@-]{2,63}")

_hasher = PasswordHasher()        # argon2id, RFC 9106 low-memory profile


class User(BaseModel):
    id: int
    name: str
    role: Role


class UsernameTaken(ValueError):
    """create_user: a user with this username already exists."""


def _utcnow() -> datetime:
    """Naive UTC, matching the DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def token_ttl() -> timedelta:
    """AUTH_TOKEN_TTL_HOURS, read on each login; a missing or invalid value means 12 hours."""
    raw = os.getenv("AUTH_TOKEN_TTL_HOURS", "").strip()
    if not raw:
        return timedelta(hours=DEFAULT_TOKEN_TTL_HOURS)
    try:
        hours = float(raw)
    except ValueError:
        hours = 0.0
    if not 0 < hours <= 24 * 366:
        logger.warning("AUTH_TOKEN_TTL_HOURS=%r is not a positive number of hours; using %s",
                       raw, DEFAULT_TOKEN_TTL_HOURS)
        hours = DEFAULT_TOKEN_TTL_HOURS
    return timedelta(hours=hours)


# --- passwords and users ---------------------------------------------------------------------------
def normalize_username(username: str) -> str:
    return username.strip().lower()


def validate_new_user(username: str, password: str, role: str) -> str:
    """Check a new user's fields; returns the normalized username or raises ValueError with a message
    that is safe to show (it never contains the password)."""
    name = normalize_username(username)
    if not USERNAME_PATTERN.fullmatch(name):
        raise ValueError("username must be 3-64 characters: letters, digits, '.', '_', '@' or '-'")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"password must be at most {MAX_PASSWORD_LENGTH} characters")
    if role not in ROLES:
        raise ValueError("role must be 'admin' or 'recruiter'")
    return name


def hash_password(password: str) -> str:
    return _hasher.hash(password)


@cache
def _dummy_hash() -> str:
    """A hash to verify against when the username is unknown, so both failures take as long."""
    return _hasher.hash(secrets.token_urlsafe(16))


def _password_matches(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):  # VerifyMismatchError is a VerificationError
        return False


def create_user(session: Session, username: str, password: str, role: str) -> models.User:
    """Validate and store a new user. Raises ValueError (bad field) or UsernameTaken."""
    name = validate_new_user(username, password, role)
    if session.query(models.User.id).filter(models.User.username == name).first() is not None:
        raise UsernameTaken(name)
    user = models.User(username=name, password_hash=hash_password(password), role=role)
    session.add(user)
    try:
        session.commit()
    except IntegrityError:          # created by a concurrent request since the check above
        session.rollback()
        raise UsernameTaken(name) from None
    return user


def authenticate(session: Session, username: str, password: str) -> models.User | None:
    """The user these credentials belong to, or None. An unknown username costs one argon2 verify,
    the same as a wrong password."""
    if len(password) > MAX_PASSWORD_LENGTH:
        return None
    user = session.query(models.User).filter(models.User.username == normalize_username(username)).one_or_none()
    if user is None:
        _password_matches(_dummy_hash(), password)
        return None
    if not _password_matches(user.password_hash, password):
        return None
    if _hasher.check_needs_rehash(user.password_hash):  # argon2 parameters were raised since it was hashed
        user.password_hash = hash_password(password)
        session.commit()
    return user


def public_user(user: models.User) -> User:
    return User(id=user.id, name=user.username, role=cast(Role, user.role))


# --- tokens ----------------------------------------------------------------------------------------
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token(session: Session, user: models.User) -> tuple[str, datetime]:
    """Start a session for `user`: returns the token (shown once, never stored) and its expiry (naive UTC).
    The user's expired sessions are deleted at the same time."""
    now = _utcnow()
    session.query(models.AuthSession).filter(models.AuthSession.user_id == user.id,
                                             models.AuthSession.expires_at <= now).delete()
    token = secrets.token_urlsafe(32)
    expires_at = now + token_ttl()
    session.add(models.AuthSession(token_hash=_token_hash(token), user_id=user.id, created_at=now,
                                   expires_at=expires_at))
    session.commit()
    return token, expires_at


def revoke_token(session: Session, token: str) -> None:
    """Log out: delete the session this token belongs to (no error if there is none)."""
    session.query(models.AuthSession).filter(models.AuthSession.token_hash == _token_hash(token)).delete()
    session.commit()


def user_for_token(session: Session, token: str) -> models.User | None:
    """The user of an unexpired session with this token, or None."""
    if not token or len(token) > MAX_TOKEN_LENGTH:
        return None
    row = (session.query(models.AuthSession)
           .filter(models.AuthSession.token_hash == _token_hash(token), models.AuthSession.expires_at > _utcnow())
           .one_or_none())
    return row.user if row is not None else None


def request_token(request: Request) -> str | None:
    """The token a request carries: an `Authorization: Bearer` header, else the session cookie."""
    header = request.headers.get("authorization", "")
    scheme, _, credentials = header.partition(" ")
    if scheme.lower() == "bearer" and credentials.strip():
        return credentials.strip()
    return request.cookies.get(SESSION_COOKIE) or None


def is_https(request: Request) -> bool:
    """True when the client connected over HTTPS, directly or through a proxy that says so. Trusting
    X-Forwarded-Proto here can only add the Secure flag, which never weakens the cookie."""
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or forwarded == "https"


# --- dependencies ----------------------------------------------------------------------------------
def require_user(request: Request, session: Annotated[Session, Depends(get_session)]) -> User:
    """The signed-in user, from the session cookie or an `Authorization: Bearer` token; 401 otherwise.
    The database session is the request's own (get_session), so overriding get_session covers auth too."""
    token = request_token(request)
    user = user_for_token(session, token) if token else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated",
                            headers={"WWW-Authenticate": "Bearer"})
    return public_user(user)


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
