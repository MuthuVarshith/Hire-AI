"""POST /api/auth/login, POST /api/auth/logout, GET /api/auth/me, GET and POST /api/auth/users
(docs/contracts.md section 3). Errors are HTTPExceptions with plain detail strings; app/main.py turns
them into {"error": ...}."""
from datetime import timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from app.auth import (SESSION_COOKIE, Admin, Recruiter, Role, User, UsernameTaken, authenticate, create_user,
                      is_https, issue_token, public_user, request_token, revoke_token, token_ttl)
from app.db import get_session

router = APIRouter(prefix="/api/auth", tags=["auth"])
DbSession = Annotated[Session, Depends(get_session)]
INVALID_LOGIN = "Invalid username or password"


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    user: User
    token: str
    expires_at: str


class UserCreateIn(BaseModel):
    username: str
    password: str
    role: str


class UserOut(BaseModel):
    id: int
    name: str
    role: Role
    created_at: str


def _user_out(user: models.User) -> UserOut:
    return UserOut(**public_user(user).model_dump(), created_at=user.created_at.isoformat())


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, session: DbSession) -> LoginOut:
    user = authenticate(session, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_LOGIN)
    token, expires_at = issue_token(session, user)
    response.set_cookie(SESSION_COOKIE, token, max_age=int(token_ttl().total_seconds()), path="/",
                        httponly=True, samesite="strict", secure=is_https(request))
    return LoginOut(user=public_user(user), token=token,
                    expires_at=expires_at.replace(tzinfo=timezone.utc).isoformat())


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: Recruiter, request: Request, session: DbSession) -> Response:
    token = request_token(request)
    if token:
        revoke_token(session, token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict", secure=is_https(request))
    return response


@router.get("/me")
def me(user: Recruiter) -> User:
    return user


@router.get("/users")
def list_users(user: Admin, session: DbSession) -> list[UserOut]:
    return [_user_out(u) for u in session.query(models.User).order_by(models.User.id)]


@router.post("/users", status_code=status.HTTP_201_CREATED)
def add_user(body: UserCreateIn, user: Admin, session: DbSession) -> UserOut:
    try:
        created = create_user(session, body.username, body.password, body.role)
    except UsernameTaken:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists") from None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return _user_out(created)
