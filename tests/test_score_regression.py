"""Scores must not change when scoring internals are refactored.

tests/fixtures/score_baseline.json was captured from the code before
`score_candidate` took a `weights` argument, when per-template weights were
applied by mutating config.WEIGHTS in place. Every case is recomputed here
through the current code path and compared field by field.
"""
import json
import platform
from functools import lru_cache
from pathlib import Path

import pytest

import config
import jd_parser
import resume_parser
import scorer

REPO = Path(__file__).resolve().parent.parent
BASELINE = json.loads((REPO / "tests" / "fixtures" / "score_baseline.json").read_text(encoding="utf-8"))
SCORE_FIELDS = ("semantic_score", "skill_match_score", "experience_score", "education_score", "composite_score")


def _environment_matches_fixture() -> bool:
    import numpy
    import sentence_transformers
    import torch

    env = BASELINE["environment"]
    return (
        env["python"] == platform.python_version()
        and env["torch"] == torch.__version__
        and env["sentence_transformers"] == sentence_transformers.__version__
        and env["numpy"] == numpy.__version__
    )


@lru_cache(maxsize=None)
def _jd(path: str):
    return jd_parser.parse_jd(str(REPO / path))


@lru_cache(maxsize=None)
def _resume(path: str):
    return resume_parser.parse_resume(str(REPO / path))


@pytest.fixture(scope="module")
def model():
    loaded = scorer.load_embedding_model()
    if loaded is None:
        pytest.skip("embedding model unavailable")
    return loaded


def test_baseline_fixture_is_complete():
    assert BASELINE["case_count"] == len(BASELINE["cases"]) == 120
    assert {c["template"] for c in BASELINE["cases"]} == {
        "Default", "AI Engineer", "Frontend Developer", "DevOps Engineer", "Data Scientist",
    }


@pytest.mark.slow
def test_scores_match_pre_refactor_baseline(model):
    # Identical environment: bit-for-bit equality. Otherwise allow one rounding step (0.01),
    # since a different torch/numpy build can shift an embedding in the last float digits.
    tolerance = 0.0 if _environment_matches_fixture() else 0.011
    mismatches = []
    for case in BASELINE["cases"]:
        result = scorer.score_candidate(_resume(case["resume"]), _jd(case["jd"]), model, weights=case["weights"])
        expected = case["result"]
        where = (case["resume"], case["jd"], case["template"])
        for field in SCORE_FIELDS:
            if abs(getattr(result, field) - expected[field]) > tolerance:
                mismatches.append((*where, field, expected[field], getattr(result, field)))
        # Compared as sets: the pre-refactor parsers built skill lists with list(set(...)),
        # so the baseline's order depended on the process hash seed. Membership must match exactly.
        for field in ("matched_skills", "missing_skills"):
            if sorted(getattr(result, field)) != sorted(expected[field]):
                mismatches.append((*where, field, expected[field], getattr(result, field)))
    assert not mismatches, f"{len(mismatches)} mismatches, first: {mismatches[:3]}"


SKILLS_ONLY = {"semantic": 0.0, "skills": 1.0, "experience": 0.0, "education": 0.0}
EDUCATION_ONLY = {"semantic": 0.0, "skills": 0.0, "experience": 0.0, "education": 1.0}


def _toy_pair():
    """Without a model: semantic 0, skills 50 (1 of 2), experience 50 (2 of 4 years), education 100."""
    resume = config.ResumeProfile(name="A", skills=["python"], experience_years=2,
                                  education=[{"degree": "Bachelor's"}], raw_text="python")
    jd = config.JobRequirements(required_skills=["python", "docker"], min_experience_years=4,
                                required_education="Bachelor's", raw_text="python docker")
    return resume, jd


def test_weights_argument_does_not_mutate_defaults():
    before = dict(config.WEIGHTS)
    scorer.score_candidate(*_toy_pair(), None, weights=SKILLS_ONLY)
    assert config.WEIGHTS == before


def test_explicit_weights_change_composite_and_default_matches_config():
    resume, jd = _toy_pair()
    default = scorer.score_candidate(resume, jd, None)
    explicit_default = scorer.score_candidate(resume, jd, None, weights=dict(config.WEIGHTS))

    assert default.composite_score == explicit_default.composite_score
    assert default.composite_score == round(0 * 0.40 + 50 * 0.30 + 50 * 0.15 + 100 * 0.15, 2)
    assert scorer.score_candidate(resume, jd, None, weights=SKILLS_ONLY).composite_score == 50.0


def test_concurrent_scoring_with_different_weights_does_not_leak():
    from concurrent.futures import ThreadPoolExecutor

    resume, jd = _toy_pair()
    jobs = [SKILLS_ONLY, EDUCATION_ONLY] * 200
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda w: scorer.score_candidate(resume, jd, None, weights=w).composite_score, jobs))
    assert results == [50.0, 100.0] * 200
