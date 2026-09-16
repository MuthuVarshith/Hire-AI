"""Database models for the Recruiting Agent."""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, Boolean, ForeignKey, JSON, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session
import enum

Base = declarative_base()


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

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description_text = Column(Text, nullable=False)
    required_skills = Column(JSON, nullable=True)  # List of skills
    preferred_skills = Column(JSON, nullable=True)  # List of skills
    min_experience_years = Column(Float, default=0.0)
    required_education = Column(String(100), default="Bachelor's")
    responsibilities = Column(JSON, nullable=True)  # List of responsibilities
    scoring_template_id = Column(Integer, ForeignKey("scoring_templates.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    candidates = relationship("Candidate", back_populates="job", cascade="all, delete-orphan")
    screening_results = relationship("ScreeningResult", back_populates="job", cascade="all, delete-orphan")
    scoring_template = relationship("ScoringTemplate", back_populates="jobs")

    def to_dict(self):
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

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True, unique=False)  # Not unique; may apply to multiple jobs
    phone = Column(String(20), nullable=True)
    resume_filename = Column(String(255), nullable=True)
    resume_text = Column(Text, nullable=True)  # Extracted resume text
    skills = Column(JSON, nullable=True)  # List of extracted skills
    experience_years = Column(Float, default=0.0)
    education = Column(JSON, nullable=True)  # List of education records
    work_history = Column(JSON, nullable=True)  # List of work history records
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    status = Column(Enum(PipelineStatus), default=PipelineStatus.SCREENED)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(Text, nullable=True)  # Recruiter notes

    # Relationships
    job = relationship("Job", back_populates="candidates")
    screening_results = relationship("ScreeningResult", back_populates="candidate", cascade="all, delete-orphan")

    def to_dict(self, include_screening=False):
        data = {
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

    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    scoring_template_id = Column(Integer, ForeignKey("scoring_templates.id"), nullable=True)

    # Scores
    composite_score = Column(Float, default=0.0)
    semantic_score = Column(Float, default=0.0)
    skill_match_score = Column(Float, default=0.0)
    experience_score = Column(Float, default=0.0)
    education_score = Column(Float, default=0.0)

    # Results
    matched_skills = Column(JSON, default=list)  # List of matched skills
    missing_skills = Column(JSON, default=list)  # List of missing skills
    matched_preferred_skills = Column(JSON, default=list)  # Matched preferred skills

    # Explanations
    reasoning = Column(Text, nullable=True)  # AI-generated reasoning
    strengths = Column(JSON, nullable=True)  # List of strengths
    skill_gaps = Column(JSON, nullable=True)  # List of gaps

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    candidate = relationship("Candidate", back_populates="screening_results")
    job = relationship("Job", back_populates="screening_results")
    scoring_template = relationship("ScoringTemplate", back_populates="screening_results")

    def to_dict(self):
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "job_id": self.job_id,
            "composite_score": round(self.composite_score, 2),
            "semantic_score": round(self.semantic_score, 2),
            "skill_match_score": round(self.skill_match_score, 2),
            "experience_score": round(self.experience_score, 2),
            "education_score": round(self.education_score, 2),
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

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Weights (must sum to 1.0)
    semantic_weight = Column(Float, default=0.40)
    skill_weight = Column(Float, default=0.30)
    experience_weight = Column(Float, default=0.15)
    education_weight = Column(Float, default=0.15)

    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    jobs = relationship("Job", back_populates="scoring_template")
    screening_results = relationship("ScreeningResult", back_populates="scoring_template")

    def to_dict(self):
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

    def validate_weights(self):
        """Ensure weights sum to 1.0."""
        total = self.semantic_weight + self.skill_weight + self.experience_weight + self.education_weight
        return abs(total - 1.0) < 1e-9

    def to_weights_dict(self):
        """Return weights in the format expected by scorer."""
        return {
            "semantic": self.semantic_weight,
            "skills": self.skill_weight,
            "experience": self.experience_weight,
            "education": self.education_weight,
        }


def init_db(database_url: str):
    """Initialize database and create all tables."""
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    return engine


def create_default_templates(session: Session):
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
