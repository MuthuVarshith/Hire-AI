"""The agent's five read-only tools: thin wrappers over retrieval, the stored rows and the scorer.

Each tool takes a Pydantic input model and returns a Pydantic output model, so the agent (and
the MCP server) can validate arguments before anything runs. No tool writes: score_candidate
returns the stored screening score, or computes one with the unchanged scorer exactly as
POST /api/screen does (screening.py) without saving it.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

import ask
import scorer
import screening
from embeddings import EmbeddingProvider
from models import Candidate, Job, ScreeningResult
from retrieval import Retriever

MAX_QUERY_CHARS = ask.MAX_QUESTION_CHARS
MAX_COMPARE = 10
MAX_ID = 2**31 - 1  # PostgreSQL INTEGER; larger ids can't exist and would overflow the driver


class ToolError(LookupError):
    """A tool could not run on valid arguments, e.g. an unknown candidate. The message is safe to show."""


def validation_message(exc: ValidationError) -> str:
    """Field paths and messages only; the rejected input values are not echoed back."""
    return "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'value'}: {e['msg']}" for e in exc.errors())


@dataclass
class ToolContext:
    session: Session
    provider: EmbeddingProvider | None
    # Looked up at call time, so tests can patch scorer.load_embedding_model as they do for the route.
    embedding_model: Callable[[], Any] = lambda: scorer.load_embedding_model()


class _Strict(BaseModel):
    # Strict: "3" is not candidate 3 and true is not job 1; unknown fields are refused.
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


Id = Field(gt=0, le=MAX_ID)
IdItem = Annotated[int, Field(gt=0, le=MAX_ID)]


# --- inputs --------------------------------------------------------------------------
class SearchInput(_Strict):
    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    job_id: int | None = Field(default=None, gt=0, le=MAX_ID)


class CandidateInput(_Strict):
    candidate_id: int = Id


class ScoreInput(_Strict):
    candidate_id: int = Id
    job_id: int = Id


class CompareInput(_Strict):
    candidate_ids: list[IdItem] = Field(min_length=2, max_length=MAX_COMPARE)
    job_id: int = Id


# --- outputs -------------------------------------------------------------------------
class ChunkCitation(_Strict):
    candidate_id: int
    candidate_name: str
    section: str
    text: str
    char_start: int          # text == candidate.resume_text[char_start:char_end]
    char_end: int
    similarity: float


class SearchOutput(_Strict):
    query: str
    hits: list[ChunkCitation]


class CandidateProfile(_Strict):
    candidate_id: int
    name: str
    job_id: int | None
    skills: list[str]
    experience_years: float | None
    degrees: list[str]
    status: str | None


class ScoreOutput(_Strict):
    candidate_id: int
    candidate_name: str
    job_id: int
    source: Literal["stored", "computed"]
    screening_id: int | None             # the stored ScreeningResult, when source is "stored"
    composite_score: float
    semantic_score: float
    skill_match_score: float
    experience_score: float
    education_score: float
    matched_skills: list[str]
    missing_skills: list[str]


class CompareOutput(_Strict):
    job_id: int
    rows: list[ScoreOutput]              # highest composite first, ties by candidate id


class SkillGapReport(_Strict):
    candidate_id: int
    job_id: int
    required_skills: list[str]
    matched_skills: list[str]
    missing_skills: list[str]
    preferred_skills: list[str]
    matched_preferred_skills: list[str]
    source: Literal["stored", "computed"]


# --- tools ---------------------------------------------------------------------------
def _candidate(ctx: ToolContext, candidate_id: int) -> Candidate:
    candidate = ctx.session.get(Candidate, candidate_id)
    if candidate is None:
        raise ToolError(f"candidate {candidate_id} not found")
    return candidate


def _job(ctx: ToolContext, job_id: int) -> Job:
    job = ctx.session.get(Job, job_id)
    if job is None:
        raise ToolError(f"job {job_id} not found")
    return job


def search_candidates(ctx: ToolContext, args: SearchInput) -> SearchOutput:
    """Resume chunks for a query, with the configuration /api/ask uses (vector only, k=8)."""
    if args.job_id is not None:
        _job(ctx, args.job_id)
    hits = Retriever(ctx.session, ctx.provider).search(args.query, ask.CHOSEN_CONFIG, job_id=args.job_id)
    rows = ctx.session.query(Candidate.id, Candidate.name).filter(Candidate.id.in_({h.candidate_id for h in hits}))
    names: dict[int, str] = {cid: name for cid, name in rows}
    return SearchOutput(query=args.query, hits=[
        ChunkCitation(candidate_id=h.candidate_id, candidate_name=names.get(h.candidate_id, ""),
                      section=h.section, text=h.text, char_start=h.char_start, char_end=h.char_end,
                      similarity=round(h.score, 4))
        for h in hits])


def get_candidate_profile(ctx: ToolContext, args: CandidateInput) -> CandidateProfile:
    c = _candidate(ctx, args.candidate_id)
    degrees = [str(e.get("degree", "")) for e in (c.education or []) if isinstance(e, dict) and e.get("degree")]
    return CandidateProfile(candidate_id=c.id, name=c.name, job_id=c.job_id, skills=list(c.skills or []),
                            experience_years=c.experience_years, degrees=degrees,
                            status=c.status.value if c.status else None)


def _latest_screening(ctx: ToolContext, candidate_id: int, job_id: int) -> ScreeningResult | None:
    return (ctx.session.query(ScreeningResult)
            .filter(ScreeningResult.candidate_id == candidate_id, ScreeningResult.job_id == job_id)
            .order_by(ScreeningResult.id.desc()).first())


def score_candidate(ctx: ToolContext, args: ScoreInput) -> ScoreOutput:
    """The latest stored screening score for this candidate and job, or a fresh one that is not saved."""
    candidate, job = _candidate(ctx, args.candidate_id), _job(ctx, args.job_id)
    stored = _latest_screening(ctx, candidate.id, job.id)
    if stored is not None:
        return ScoreOutput(
            candidate_id=candidate.id, candidate_name=candidate.name, job_id=job.id, source="stored",
            screening_id=stored.id, composite_score=stored.composite_score or 0.0,
            semantic_score=stored.semantic_score or 0.0, skill_match_score=stored.skill_match_score or 0.0,
            experience_score=stored.experience_score or 0.0, education_score=stored.education_score or 0.0,
            matched_skills=list(stored.matched_skills or []), missing_skills=list(stored.missing_skills or []))
    _, _, result = screening.compute_score(ctx.session, candidate, job, ctx.embedding_model())
    return ScoreOutput(
        candidate_id=candidate.id, candidate_name=candidate.name, job_id=job.id, source="computed",
        screening_id=None, composite_score=result.composite_score, semantic_score=result.semantic_score,
        skill_match_score=result.skill_match_score, experience_score=result.experience_score,
        education_score=result.education_score, matched_skills=list(result.matched_skills),
        missing_skills=list(result.missing_skills))


def compare_candidates(ctx: ToolContext, args: CompareInput) -> CompareOutput:
    rows = [score_candidate(ctx, ScoreInput(candidate_id=cid, job_id=args.job_id))
            for cid in dict.fromkeys(args.candidate_ids)]
    rows.sort(key=lambda r: (-r.composite_score, r.candidate_id))
    return CompareOutput(job_id=args.job_id, rows=rows)


def skill_gap_report(ctx: ToolContext, args: ScoreInput) -> SkillGapReport:
    """Required skills split into matched and missing by the scorer's own output."""
    score = score_candidate(ctx, args)
    job, candidate = _job(ctx, args.job_id), _candidate(ctx, args.candidate_id)
    preferred = list(job.preferred_skills or [])
    have = candidate.skills or []
    return SkillGapReport(
        candidate_id=args.candidate_id, job_id=args.job_id, required_skills=list(job.required_skills or []),
        matched_skills=score.matched_skills, missing_skills=score.missing_skills, preferred_skills=preferred,
        # The same rule the screen route stores as matched_preferred_skills.
        matched_preferred_skills=[s for s in preferred if s in have], source=score.source)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[_Strict]
    run: Callable[[ToolContext, Any], BaseModel]


TOOLS: dict[str, ToolSpec] = {spec.name: spec for spec in (
    ToolSpec("search_candidates", "Search resume passages; returns chunk citations with offsets.",
             SearchInput, search_candidates),
    ToolSpec("get_candidate_profile", "A candidate's parsed profile: skills, experience, degrees.",
             CandidateInput, get_candidate_profile),
    ToolSpec("score_candidate", "The candidate's deterministic score for a job (stored, or computed, never saved).",
             ScoreInput, score_candidate),
    ToolSpec("compare_candidates", "Scores for 2-10 candidates on one job, highest first.",
             CompareInput, compare_candidates),
    ToolSpec("skill_gap_report", "A job's required skills split into the candidate's matched and missing.",
             ScoreInput, skill_gap_report),
)}


def call(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> BaseModel:
    """Validate arguments against the tool's model and run it. Raises KeyError, ValidationError or ToolError."""
    spec = TOOLS[name]
    return spec.run(ctx, spec.input_model.model_validate(arguments))
