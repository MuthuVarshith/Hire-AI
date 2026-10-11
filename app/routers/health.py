"""GET /api/health and GET /api/info (public)."""
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    status: str
    message: str


class InfoOut(BaseModel):
    name: str
    version: str
    endpoints: list[str]


@router.get("/api/health")
def health_check() -> HealthOut:
    return HealthOut(status="OK", message="Recruiting Agent Backend is running")


@router.get("/api/info")
def info(request: Request) -> InfoOut:
    # The OpenAPI paths: every included router's routes, already without {name:int} convertors.
    endpoints = [f"{method.upper()} {path}" for path, ops in request.app.openapi()["paths"].items()
                 if path.startswith("/api/") for method in ops]
    return InfoOut(name="AI Resume Screening Agent", version=request.app.version, endpoints=endpoints)
