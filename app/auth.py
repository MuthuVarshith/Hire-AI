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
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel

Role = Literal["admin", "recruiter"]
SESSION_COOKIE = "hireai_session"


class User(BaseModel):
    id: int
    name: str
    role: Role


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
