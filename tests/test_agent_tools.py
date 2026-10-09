"""The agent's read-only tools: strict argument models, stored vs computed scores, and no writes."""
import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

import agent_tools
import config
import indexing
import scorer
import screening
from agent_tools import (CandidateInput, CompareInput, ScoreInput, SearchInput, ToolContext, ToolError)
from database import create_database_engine
from models import Candidate, Job, ScreeningResult
from tests.test_retrieval import RESUMES, KeywordProvider

PROFILES = {
    "Ada": dict(skills=["python", "fastapi", "docker", "postgresql"], experience_years=6.0,
                education=[{"degree": "Bachelor's", "field": "CS"}]),
    "Bo": dict(skills=["react", "typescript", "css"], experience_years=2.0, education=[]),
    "Cy": dict(skills=["kubernetes", "terraform", "aws"], experience_years=4.0,
               education=[{"degree": "Master's", "field": "Systems"}]),
}
STORED_COMPOSITE = 12.34  # a sentinel no formula produces here, to tell a stored score from a computed one


def make_pool(session: Session, provider) -> dict[str, int]:
    """Two jobs and three indexed candidates on job 'Backend'; Ada has one stored screening result."""
    backend = Job(title="Backend", description_text="Backend engineer: Python, FastAPI, Docker, Kubernetes.",
                  required_skills=["python", "fastapi", "docker", "kubernetes"], preferred_skills=["postgresql"],
                  min_experience_years=3.0, required_education="Bachelor's")
    other = Job(title="Other", description_text="Frontend: React.", required_skills=["react"])
    session.add_all([backend, other])
    for name, text in RESUMES.items():
        session.add(Candidate(name=name, job=backend, resume_filename=f"{name}.txt", resume_text=text,
                              **PROFILES[name]))
    session.flush()
    ids = {c.name: c.id for c in session.query(Candidate)}
    for candidate in session.query(Candidate):
        indexing.index_candidate(session, candidate, provider)
    session.add(ScreeningResult(candidate_id=ids["Ada"], job_id=backend.id, composite_score=STORED_COMPOSITE,
                                semantic_score=1.0, skill_match_score=2.0, experience_score=3.0,
                                education_score=4.0, matched_skills=["python"], missing_skills=["kubernetes"]))
    session.commit()
    return {**ids, "backend": backend.id, "other": other.id}


@pytest.fixture
def no_model(monkeypatch):
    monkeypatch.setattr(scorer, "load_embedding_model", lambda: None)


@pytest.fixture
def pool(tmp_path, no_model):
    engine = create_database_engine(f"sqlite:///{(tmp_path / 'agent.db').as_posix()}")
    provider = KeywordProvider()
    with Session(engine) as session:
        ids = make_pool(session, provider)
        yield ToolContext(session=session, provider=provider), ids
    engine.dispose()


def test_search_returns_chunk_citations_with_exact_offsets(pool):
    ctx, ids = pool
    out = agent_tools.search_candidates(ctx, SearchInput(query="Kubernetes and Terraform", job_id=ids["backend"]))
    assert out.hits and out.hits[0].candidate_name == "Cy"
    for hit in out.hits:
        assert RESUMES[hit.candidate_name][hit.char_start:hit.char_end] == hit.text
    assert agent_tools.search_candidates(ctx, SearchInput(query="Kubernetes", job_id=ids["other"])).hits == []


def test_profile(pool):
    ctx, ids = pool
    profile = agent_tools.get_candidate_profile(ctx, CandidateInput(candidate_id=ids["Cy"]))
    assert (profile.name, profile.skills, profile.degrees) == ("Cy", PROFILES["Cy"]["skills"], ["Master's"])


def test_score_returns_the_stored_result_when_there_is_one(pool):
    ctx, ids = pool
    out = agent_tools.score_candidate(ctx, ScoreInput(candidate_id=ids["Ada"], job_id=ids["backend"]))
    assert (out.source, out.composite_score, out.missing_skills) == ("stored", STORED_COMPOSITE, ["kubernetes"])


def test_score_is_computed_like_the_screen_route_and_not_saved(pool):
    ctx, ids = pool
    session = ctx.session
    out = agent_tools.score_candidate(ctx, ScoreInput(candidate_id=ids["Cy"], job_id=ids["backend"]))
    cy, job = session.get(Candidate, ids["Cy"]), session.get(Job, ids["backend"])
    expected = scorer.score_candidate(screening.resume_profile(cy), screening.job_requirements(job), None,
                                      weights=config.WEIGHTS)
    assert out.source == "computed" and out.screening_id is None
    assert (out.composite_score, out.skill_match_score, out.matched_skills, out.missing_skills) == (
        expected.composite_score, expected.skill_match_score, expected.matched_skills, expected.missing_skills)
    assert session.query(ScreeningResult).count() == 1


def test_compare_ranks_by_score_and_skill_gap_uses_scorer_output(pool):
    ctx, ids = pool
    compared = agent_tools.compare_candidates(
        ctx, CompareInput(candidate_ids=[ids["Bo"], ids["Cy"], ids["Ada"]], job_id=ids["backend"]))
    scores = [r.composite_score for r in compared.rows]
    assert scores == sorted(scores, reverse=True) and len(scores) == 3
    gap = agent_tools.skill_gap_report(ctx, ScoreInput(candidate_id=ids["Cy"], job_id=ids["backend"]))
    computed = agent_tools.score_candidate(ctx, ScoreInput(candidate_id=ids["Cy"], job_id=ids["backend"]))
    assert (gap.matched_skills, gap.missing_skills) == (computed.matched_skills, computed.missing_skills)
    assert gap.required_skills == ["python", "fastapi", "docker", "kubernetes"]
    ada = agent_tools.skill_gap_report(ctx, ScoreInput(candidate_id=ids["Ada"], job_id=ids["backend"]))
    assert ada.matched_preferred_skills == ["postgresql"]


@pytest.mark.parametrize("name,args", [
    ("score_candidate", {"candidate_id": "1", "job_id": 1}),        # strings are not ids
    ("score_candidate", {"candidate_id": True, "job_id": 1}),       # nor are booleans
    ("score_candidate", {"candidate_id": 1, "job_id": 1, "composite_score": 100}),  # unknown field
    ("get_candidate_profile", {"candidate_id": 0}),
    ("compare_candidates", {"candidate_ids": [1], "job_id": 1}),
    ("search_candidates", {"query": ""}),
])
def test_invalid_arguments_are_refused_before_running(pool, name, args):
    ctx, _ = pool
    with pytest.raises(ValidationError):
        agent_tools.call(ctx, name, args)


def test_unknown_records_are_tool_errors(pool):
    ctx, ids = pool
    with pytest.raises(ToolError):
        agent_tools.call(ctx, "score_candidate", {"candidate_id": 999, "job_id": ids["backend"]})
    with pytest.raises(ToolError):
        agent_tools.call(ctx, "search_candidates", {"query": "python", "job_id": 999})


def test_only_the_five_read_only_tools_exist():
    assert set(agent_tools.TOOLS) == {"search_candidates", "get_candidate_profile", "score_candidate",
                                      "compare_candidates", "skill_gap_report"}
