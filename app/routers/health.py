"""GET /api/health and GET /api/info (public)."""
import re

from fastapi import APIRouter, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel

router = APIRouter(tags=["health"])
_CONVERTOR = re.compile(r":\w+}")  # {job_id:int} -> {job_id}


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
    endpoints = [f"{method} {_CONVERTOR.sub('}', route.path)}"
                 for route in request.app.routes
                 if isinstance(route, APIRoute) and route.path.startswith("/api/")
                 for method in sorted(route.methods)]
    return InfoOut(name="AI Resume Screening Agent", version=request.app.version, endpoints=endpoints)
