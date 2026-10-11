"""Scoring templates: /api/scoring-templates (recruiter)."""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Recruiter
from app.routers._shared import DbSession, JsonRequired
from app.schemas.common import MessageOut
from app.schemas.templates import WEIGHTS, TemplateCreate, TemplateOut, TemplateUpdate
from models import ScoringTemplate

logger = logging.getLogger(__name__)
router = APIRouter(tags=["scoring templates"])
DUPLICATE = "A scoring template with this name already exists"


def _template_name_taken(session: Session, name: str) -> bool:
    return session.query(ScoringTemplate.id).filter(ScoringTemplate.name == name).first() is not None


def _template_or_404(session: Session, template_id: int) -> ScoringTemplate:
    template = session.get(ScoringTemplate, template_id)
    if template is None:
        raise HTTPException(404, "Template not found")
    return template


@router.post("/api/scoring-templates", status_code=201, response_model=TemplateOut)
def create_scoring_template(user: Recruiter, _json: JsonRequired, body: TemplateCreate,
                            session: DbSession) -> dict[str, Any]:
    if not body.name:
        raise HTTPException(400, "name is required")
    if abs(sum(getattr(body, w) for w in WEIGHTS) - 1.0) > 1e-9:
        raise HTTPException(400, "Weights must sum to 1.0")
    if _template_name_taken(session, body.name):
        raise HTTPException(409, DUPLICATE)
    template = ScoringTemplate(name=body.name, description=body.description, is_default=body.is_default,
                               **{w: getattr(body, w) for w in WEIGHTS})
    session.add(template)
    try:
        session.commit()
    except IntegrityError:
        # Backstop for two requests creating the same name at once; the pre-check covers the normal case.
        session.rollback()
        raise HTTPException(409, DUPLICATE) from None
    session.refresh(template)
    logger.info("Created scoring template %s: %s", template.id, template.name)
    return template.to_dict()


@router.get("/api/scoring-templates", response_model=list[TemplateOut])
def list_scoring_templates(user: Recruiter, session: DbSession) -> list[dict[str, Any]]:
    return [t.to_dict() for t in session.query(ScoringTemplate).order_by(ScoringTemplate.name).all()]


@router.get("/api/scoring-templates/{template_id:int}", response_model=TemplateOut)
def get_scoring_template(template_id: int, user: Recruiter, session: DbSession) -> dict[str, Any]:
    return _template_or_404(session, template_id).to_dict()


@router.put("/api/scoring-templates/{template_id:int}", response_model=TemplateOut)
def update_scoring_template(template_id: int, user: Recruiter, _json: JsonRequired, body: TemplateUpdate,
                            session: DbSession) -> dict[str, Any]:
    template = _template_or_404(session, template_id)
    sent = body.model_fields_set
    # Check before assigning: queries autoflush pending changes, which would hit the unique index.
    if body.name is not None and body.name != template.name and _template_name_taken(session, body.name):
        raise HTTPException(409, DUPLICATE)
    for field in ("name", "description", *WEIGHTS):
        if field in sent:
            setattr(template, field, getattr(body, field))
    if not template.validate_weights():
        session.rollback()
        raise HTTPException(400, "Weights must sum to 1.0")
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, DUPLICATE) from None
    logger.info("Updated template %s", template_id)
    return template.to_dict()


@router.delete("/api/scoring-templates/{template_id:int}", response_model=MessageOut)
def delete_scoring_template(template_id: int, user: Recruiter, session: DbSession) -> dict[str, str]:
    template = _template_or_404(session, template_id)
    if template.is_default:
        raise HTTPException(400, "Cannot delete default template")
    session.delete(template)
    session.commit()
    logger.info("Deleted template %s", template_id)
    return {"message": "Template deleted"}
