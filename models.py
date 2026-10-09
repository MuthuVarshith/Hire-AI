"""Database models for the Recruiting Agent (SQLAlchemy 2.0 typed declarative style)."""
import enum
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (JSON, Boolean, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
                        create_engine)
from sqlalchemy.engine import Dialect, Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, TypeEngine


def _utcnow() -> datetime:
    """Naive UTC, the same values the deprecated datetime.utcnow() produced."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class EmbeddingVector(TypeDecorator[list[float]]):
    """An embedding: pgvector's `vector` on PostgreSQL, a JSON array elsewhere (SQLite).

    No fixed dimension, so vectors from different providers can coexist; each row also
    records the model that produced it, and vectors are only compared within one model.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector())
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Optional[list[float]], dialect: Dialect) -> Optional[list[float]]:
        return None if value is None else [float(x) for x in value]

    def process_result_value(self, value: Any, dialect: Dialect) -> Optional[list[float]]:
        return None if value is None else [float(x) for x in value]  # pgvector returns a numpy array


class PipelineStatus(enum.Enum):
    """Candidate pipeline status."""
    SCREENED = "Screened"
    SHORTLISTED = "Shortlisted"
    INTERVIEW = "Interview"
    OFFER = "Offer"
    HIRED = "Hired"
    REJECTED = "Rejected"


class Job(Base):
    """Job posting."""
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description_text: Mapped[str] = mapped_column(Text, nullable=False)
    required_skills: Mapped[Optional[list[str]]] = mapped_column(JSON)
    preferred_skills: Mapped[Optional[list[str]]] = mapped_column(JSON)
    min_experience_years: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    required_education: Mapped[Optional[str]] = mapped_column(String(100), default="Bachelor's")
    responsibilities: Mapped[Optional[list[str]]] = mapped_column(JSON)
    scoring_template_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("scoring_templates.id"))
    created_at: Mapped[Optional[datetime]] = mapped_column(default=_utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(default=_utcnow, onupdate=_utcnow)

    candidates: Mapped[list["Candidate"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    screening_results: Mapped[list["ScreeningResult"]] = relationship(
        back_populates="job", cascade="all, delete-orphan")
    scoring_template: Mapped[Optional["ScoringTemplate"]] = relationship(back_populates="jobs")
    chunks: Mapped[list["JobChunk"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="JobChunk.chunk_index")

    def to_dict(self) -> dict[str, Any]:
        hired = sum(1 for c in self.candidates if c.status == PipelineStatus.HIRED)
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description_text or "",
            "required_skills": self.required_skills or [],
            "preferred_skills": self.preferred_skills or [],
            "min_experience_years": self.min_experience_years,
            "required_education": self.required_education,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "candidates_count": len(self.candidates),
            # Derived from candidate records; the Job table has no status column.
            "status": "Filled" if hired else "Open",
        }


class Candidate(Base):
    """Job candidate."""
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))  # Not unique; may apply to multiple jobs
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    resume_filename: Mapped[Optional[str]] = mapped_column(String(255))
    resume_text: Mapped[Optional[str]] = mapped_column(Text)
    skills: Mapped[Optional[list[str]]] = mapped_column(JSON)
    experience_years: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    education: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON)
    work_history: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON)
    job_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("jobs.id"))
    status: Mapped[Optional[PipelineStatus]] = mapped_column(Enum(PipelineStatus), default=PipelineStatus.SCREENED)
    created_at: Mapped[Optional[datetime]] = mapped_column(default=_utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(default=_utcnow, onupdate=_utcnow)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    job: Mapped[Optional[Job]] = relationship(back_populates="candidates")
    screening_results: Mapped[list["ScreeningResult"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan")
    chunks: Mapped[list["ResumeChunk"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="ResumeChunk.chunk_index")

    def to_dict(self, include_screening: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "resume_filename": self.resume_filename,
            "skills": self.skills or [],
            "experience_years": self.experience_years,
            "education": self.education or [],
            "work_history": self.work_history or [],
            "status": self.status.value if self.status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "notes": self.notes,
            "job_id": self.job_id,
            "job_title": self.job.title if self.job else None,
        }
        if include_screening and self.screening_results:
            data["latest_screening"] = self.screening_results[-1].to_dict()
        return data


class ScreeningResult(Base):
    """Screening result for a candidate against a job."""
    __tablename__ = "screening_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(Integer, ForeignKey("candidates.id"), nullable=False)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), nullable=False)
    scoring_template_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("scoring_templates.id"))

    composite_score: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    semantic_score: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    skill_match_score: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    experience_score: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    education_score: Mapped[Optional[float]] = mapped_column(Float, default=0.0)

    matched_skills: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    missing_skills: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    matched_preferred_skills: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)

    reasoning: Mapped[Optional[str]] = mapped_column(Text)  # Template text, or AI-generated when a key is set
    strengths: Mapped[Optional[list[str]]] = mapped_column(JSON)
    skill_gaps: Mapped[Optional[list[str]]] = mapped_column(JSON)

    created_at: Mapped[Optional[datetime]] = mapped_column(default=_utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(default=_utcnow, onupdate=_utcnow)

    candidate: Mapped[Candidate] = relationship(back_populates="screening_results")
    job: Mapped[Job] = relationship(back_populates="screening_results")
    scoring_template: Mapped[Optional["ScoringTemplate"]] = relationship(back_populates="screening_results")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "job_id": self.job_id,
            "composite_score": round(self.composite_score or 0.0, 2),
            "semantic_score": round(self.semantic_score or 0.0, 2),
            "skill_match_score": round(self.skill_match_score or 0.0, 2),
            "experience_score": round(self.experience_score or 0.0, 2),
            "education_score": round(self.education_score or 0.0, 2),
            "matched_skills": self.matched_skills or [],
            "missing_skills": self.missing_skills or [],
            "matched_preferred_skills": self.matched_preferred_skills or [],
            "reasoning": self.reasoning,
            "strengths": self.strengths or [],
            "skill_gaps": self.skill_gaps or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ScoringTemplate(Base):
    """Reusable scoring configuration for different roles."""
    __tablename__ = "scoring_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Weights (must sum to 1.0)
    semantic_weight: Mapped[Optional[float]] = mapped_column(Float, default=0.40)
    skill_weight: Mapped[Optional[float]] = mapped_column(Float, default=0.30)
    experience_weight: Mapped[Optional[float]] = mapped_column(Float, default=0.15)
    education_weight: Mapped[Optional[float]] = mapped_column(Float, default=0.15)

    is_default: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(default=_utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(default=_utcnow, onupdate=_utcnow)

    jobs: Mapped[list[Job]] = relationship(back_populates="scoring_template")
    screening_results: Mapped[list[ScreeningResult]] = relationship(back_populates="scoring_template")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "semantic_weight": self.semantic_weight,
            "skill_weight": self.skill_weight,
            "experience_weight": self.experience_weight,
            "education_weight": self.education_weight,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def validate_weights(self) -> bool:
        """Ensure weights sum to 1.0."""
        total = sum(self.to_weights_dict().values())
        return abs(total - 1.0) < 1e-9

    def to_weights_dict(self) -> dict[str, float]:
        """Return weights in the format expected by scorer."""
        return {
            "semantic": self.semantic_weight or 0.0,
            "skills": self.skill_weight or 0.0,
            "experience": self.experience_weight or 0.0,
            "education": self.education_weight or 0.0,
        }


class ResumeChunk(Base):
    """A section-aware piece of a candidate's resume, with its embedding (see chunking.py)."""
    __tablename__ = "resume_chunks"
    __table_args__ = (UniqueConstraint("candidate_id", "chunk_index", name="uq_resume_chunks_candidate_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(String(32), nullable=False)
    heading: Mapped[Optional[str]] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)  # text == resume_text[char_start:char_end]
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    source_file: Mapped[Optional[str]] = mapped_column(String(255))
    embedding: Mapped[Optional[list[float]]] = mapped_column(EmbeddingVector())
    embedding_model: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[Optional[datetime]] = mapped_column(default=_utcnow)

    candidate: Mapped[Candidate] = relationship(back_populates="chunks")


class JobChunk(Base):
    """A section-aware piece of a job description, with its embedding (see chunking.py)."""
    __tablename__ = "job_chunks"
    __table_args__ = (UniqueConstraint("job_id", "chunk_index", name="uq_job_chunks_job_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(String(32), nullable=False)
    heading: Mapped[Optional[str]] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)  # text == description_text[char_start:char_end]
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(EmbeddingVector())
    embedding_model: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[Optional[datetime]] = mapped_column(default=_utcnow)

    job: Mapped[Job] = relationship(back_populates="chunks")



class AgentShortlist(Base):
    """A shortlist the agent proposed and a human approved (POST /api/agent/approve/<thread_id>).

    Only the approval endpoint creates rows; the agent can propose, never approve. `entries` is a
    snapshot taken at approval: each candidate's id, name, score from the score_candidate tool and
    the resume passages cited for them. It is an audit record, so it outlives the job (job_id is set
    to NULL where foreign keys are enforced; job_title keeps the name) and the candidates (their
    names are in `entries`).
    """
    __tablename__ = "agent_shortlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    job_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), index=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(255))
    request: Mapped[str] = mapped_column(Text, nullable=False)
    entries: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    # Proposed candidates deleted before approval, left out of `entries`.
    dropped_ids: Mapped[Optional[list[int]]] = mapped_column(JSON)
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False)  # self-declared until the app has auth
    approved_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    note: Mapped[Optional[str]] = mapped_column(Text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "job_id": self.job_id,
            "job_title": self.job_title,
            "request": self.request,
            "entries": self.entries,
            "dropped_ids": self.dropped_ids or [],
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
            "note": self.note,
        }


class AgentDecision(Base):
    """Every human decision on a proposed shortlist, approve or reject.

    The row is inserted before the paused run resumes, and thread_id is UNIQUE, so it is the atomic
    claim on the run: of two decisions sent together, one inserts and the other is refused.
    `outcome` is set after the run resumes: approved, rejected, job_deleted or candidates_deleted.
    """
    __tablename__ = "agent_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(255), nullable=False)  # self-declared until the app has auth
    note: Mapped[Optional[str]] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    job_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), index=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(255))
    request: Mapped[Optional[str]] = mapped_column(Text)
    entries: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON)  # the proposal as the reviewer saw it
    outcome: Mapped[Optional[str]] = mapped_column(String(32))

def init_db(database_url: str) -> Engine:
    """Initialize database and create all tables."""
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    return engine


def create_default_templates(session: Session) -> None:
    """Create default scoring templates if they don't exist."""
    if session.query(ScoringTemplate).filter_by(name="Default").first():
        return

    templates = [
        ScoringTemplate(
            name="Default",
            description="Default balanced scoring for all roles",
            semantic_weight=0.40,
            skill_weight=0.30,
            experience_weight=0.15,
            education_weight=0.15,
            is_default=True,
        ),
        ScoringTemplate(
            name="AI Engineer",
            description="Emphasizes semantic relevance and skills for AI roles",
            semantic_weight=0.35,
            skill_weight=0.35,
            experience_weight=0.20,
            education_weight=0.10,
        ),
        ScoringTemplate(
            name="Frontend Developer",
            description="Balanced skills and semantic match for frontend roles",
            semantic_weight=0.30,
            skill_weight=0.40,
            experience_weight=0.20,
            education_weight=0.10,
        ),
        ScoringTemplate(
            name="DevOps Engineer",
            description="Experience and hands-on skills priority for DevOps",
            semantic_weight=0.25,
            skill_weight=0.40,
            experience_weight=0.25,
            education_weight=0.10,
        ),
        ScoringTemplate(
            name="Data Scientist",
            description="Education and technical skills focus for data roles",
            semantic_weight=0.35,
            skill_weight=0.35,
            experience_weight=0.15,
            education_weight=0.15,
        ),
    ]

    for template in templates:
        session.add(template)
    session.commit()
