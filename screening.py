"""Scoring a stored candidate against a stored job, shared by the screen route and the agent tools.

The inputs are built from the database rows exactly as POST /api/screen always built them, so
the agent's score_candidate tool computes the same numbers as the route. Nothing here writes.
"""
from typing import Any

from sqlalchemy.orm import Session

import config as cfg
import scorer
from models import Candidate, Job, ScoringTemplate


def job_requirements(job: Job) -> cfg.JobRequirements:
    return cfg.JobRequirements(
        title=job.title,
        required_skills=job.required_skills or [],
        preferred_skills=job.preferred_skills or [],
        min_experience_years=job.min_experience_years,  # type: ignore[arg-type]  # as the route passed it
        required_education=job.required_education,  # type: ignore[arg-type]
        responsibilities=job.responsibilities or [],
        raw_text=job.description_text,
    )


def resume_profile(candidate: Candidate) -> cfg.ResumeProfile:
    return cfg.ResumeProfile(
        name=candidate.name,
        email=candidate.email,  # type: ignore[arg-type]  # as the route passed it
        phone=candidate.phone,  # type: ignore[arg-type]
        skills=candidate.skills or [],
        experience_years=candidate.experience_years,  # type: ignore[arg-type]
        education=candidate.education or [],
        work_history=candidate.work_history or [],
        raw_text=candidate.resume_text,  # type: ignore[arg-type]
        file_path=candidate.resume_filename or "",
    )


def job_weights(session: Session, job: Job) -> dict[str, float]:
    """The job's scoring template weights, or the defaults when it has none (or it was deleted)."""
    if job.scoring_template_id:
        template = session.query(ScoringTemplate).filter(ScoringTemplate.id == job.scoring_template_id).first()
        if template:
            return template.to_weights_dict()
    return cfg.WEIGHTS


def compute_score(session: Session, candidate: Candidate, job: Job,
                  embedding_model: Any) -> tuple[cfg.ResumeProfile, cfg.JobRequirements, cfg.CandidateScore]:
    """Score with the unchanged scorer; returns the inputs too, since the route reuses them."""
    resume = resume_profile(candidate)
    requirements = job_requirements(job)
    result = scorer.score_candidate(resume, requirements, embedding_model, weights=job_weights(session, job))
    return resume, requirements, result
