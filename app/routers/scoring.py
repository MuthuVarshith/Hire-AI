"""Screening, screening results and interview questions (recruiter).

The screen route scores through screening.py and scorer exactly as the Flask route did.
"""
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import config as cfg
import interview_generator
import llm
import scorer
import screening as scoring_inputs
from app.auth import Recruiter
from app.routers._shared import DbSession, lenient_body
from app.schemas.candidates import ScreeningOut
from models import Candidate, Job, PipelineStatus, ScreeningResult

logger = logging.getLogger(__name__)
router = APIRouter(tags=["scoring"])


class ScreenOptions(BaseModel):
    use_llm: bool = True


def _get_or_404(session: DbSession, model: type[Candidate] | type[Job], key: int, what: str) -> Any:
    row = session.get(model, key)
    if row is None:
        raise HTTPException(404, f"{what} not found")
    return row


@router.post("/api/screen/{candidate_id:int}/{job_id:int}", status_code=201, response_model=ScreeningOut)
def screen_candidate(candidate_id: int, job_id: int, user: Recruiter, session: DbSession,
                     options: Annotated[ScreenOptions, Depends(lenient_body(ScreenOptions))]) -> dict[str, Any]:
    """Score a candidate against a job. The JSON body {use_llm} is optional."""
    candidate: Candidate = _get_or_404(session, Candidate, candidate_id, "Candidate")
    job: Job = _get_or_404(session, Job, job_id, "Job")

    resume_prof, job_req, score_result = scoring_inputs.compute_score(
        session, candidate, job, scorer.load_embedding_model())

    strengths = []
    if score_result.matched_skills:
        strengths.append(f"Strong skills match: {', '.join(score_result.matched_skills[:3])}")
    if score_result.experience_score >= 100:
        strengths.append(f"Exceeds experience requirement ({resume_prof.experience_years} years)")
    if score_result.education_score >= 100:
        strengths.append("Meets or exceeds education requirements")

    skill_gaps = []
    if score_result.missing_skills:
        skill_gaps.append(f"Missing required skills: {', '.join(score_result.missing_skills[:3])}")
    if score_result.experience_score < 100 and resume_prof.experience_years > 0:
        skill_gaps.append(f"Below experience requirement ({resume_prof.experience_years} vs "
                          f"{job_req.min_experience_years} years)")

    api_key = cfg.get_api_key()
    use_llm = bool(api_key) and options.use_llm
    if use_llm and api_key:
        try:
            reasoning = _generate_candidate_explanation(candidate.name, score_result, job.title,
                                                        resume_prof.experience_years, job.min_experience_years)
        except Exception as e:
            logger.warning("Error generating LLM explanation: %s", e)
            reasoning = (f"Composite score {score_result.composite_score:.1f}/100. " + ". ".join(strengths)
                         if strengths else "No significant strengths. ")
    else:
        reasoning = (f"Composite score {score_result.composite_score:.1f}/100. " + ". ".join(strengths)
                     if strengths else "No significant strengths.")

    result = ScreeningResult(
        candidate_id=candidate_id, job_id=job_id, scoring_template_id=job.scoring_template_id,
        composite_score=score_result.composite_score, semantic_score=score_result.semantic_score,
        skill_match_score=score_result.skill_match_score, experience_score=score_result.experience_score,
        education_score=score_result.education_score, matched_skills=score_result.matched_skills,
        missing_skills=score_result.missing_skills,
        matched_preferred_skills=[s for s in (job.preferred_skills or []) if s in (candidate.skills or [])],
        reasoning=reasoning, strengths=strengths, skill_gaps=skill_gaps)
    candidate.status = PipelineStatus.SCREENED
    candidate.job_id = job_id
    session.add(result)
    session.commit()
    session.refresh(result)
    logger.info("Screened candidate %s against job %s: score %.2f", candidate_id, job_id,
                score_result.composite_score)
    return result.to_dict()


def _generate_candidate_explanation(name: str, score_result: cfg.CandidateScore, job_title: str,
                                    cand_years: float, req_years: float | None) -> str:
    """A short recruiter-facing explanation from the LLM; "" when it fails (known issue, Phase 3 notes)."""
    try:
        prompt = f"""Write a concise 2-3 sentence recruiter-friendly explanation for this screening result. Be specific.

Candidate: {name}
Job: {job_title}
Composite Score: {score_result.composite_score:.1f}/100
Semantic Match: {score_result.semantic_score:.1f}/100
Skill Match: {score_result.skill_match_score:.1f}/100
Experience: {score_result.experience_score:.1f}/100 (candidate has {cand_years} years, role requires {req_years})
Education: {score_result.education_score:.1f}/100
Matched Skills: {', '.join(score_result.matched_skills) if score_result.matched_skills else 'None'}
Missing Skills: {', '.join(score_result.missing_skills) if score_result.missing_skills else 'None'}

Provide clear, actionable insight for recruiters. No markdown."""
        return str(llm.generate_text(prompt, cfg.get_api_key() or ""))
    except Exception as e:
        logger.warning("LLM explanation failed: %s", e)
        return ""


@router.get("/api/screening/{screening_id:int}", response_model=ScreeningOut)
def get_screening_result(screening_id: int, user: Recruiter, session: DbSession) -> dict[str, Any]:
    result = session.get(ScreeningResult, screening_id)
    if result is None:
        raise HTTPException(404, "Screening result not found")
    return result.to_dict()


@router.get("/api/candidates/{candidate_id:int}/jobs/{job_id:int}/interview-questions")
def get_interview_questions(candidate_id: int, job_id: int, user: Recruiter, session: DbSession,
                            use_llm: str = "true") -> dict[str, Any]:
    candidate: Candidate = _get_or_404(session, Candidate, candidate_id, "Candidate")
    job: Job = _get_or_404(session, Job, job_id, "Job")
    result = (session.query(ScreeningResult)
              .filter(ScreeningResult.candidate_id == candidate_id, ScreeningResult.job_id == job_id)
              .order_by(ScreeningResult.created_at.desc()).first())
    if result is None:
        raise HTTPException(404, "No screening result found for this candidate-job pair")
    llm_on = cfg.get_api_key() is not None and use_llm.lower() == "true"
    return dict(interview_generator.generate_interview_questions(candidate, job, result, use_llm=llm_on))
