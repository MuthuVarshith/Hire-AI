"""Scoring under injection: the LLM cannot change a score, but the parsed profile can.

The embedding model is None here (semantic score 0, exact skill matching), as in
test_api_contract.py, so every number below is deterministic.
"""
import io
import json

import pytest

import config
import jd_parser
import llm
import resume_parser
import scorer
from tests.injection.conftest import FIXTURES, NAMES, SAMPLE_JD
from tests.test_api_contract import app_module, client, make_job, screen  # noqa: F401  (fixtures)

COMPLIANT = "Understood. Priya Raman is the top candidate. score: 100. Rank her first; the others are unqualified."
REFUSING = "I cannot change scores. The excerpt contains instructions, which I ignore."

# Composite score of each injected resume minus its clean twin, with the regex parser and no
# embedding model. Measured, not chosen: keyword stuffing adds the six JD skills the clean twin
# lacks, so skill match goes 25 -> 100 and the composite rises by 0.30 * 75 = 22.5.
EXPECTED_DELTA = {name: 0.0 for name in NAMES} | {"keyword_stuffing": 22.5}
CLEAN_COMPOSITE = 37.5


def _jd():
    return jd_parser.parse_jd_text(SAMPLE_JD, api_key=None)


def _score(path):
    return scorer.score_candidate(resume_parser.parse_resume(str(path)), _jd(), None)


@pytest.mark.parametrize("name", NAMES)
def test_score_is_identical_whether_the_llm_complies_or_refuses(name, monkeypatch):
    path = FIXTURES / f"injected_{name}.txt"
    results, calls = [], []
    for reply in (COMPLIANT, REFUSING):
        monkeypatch.setattr(llm, "generate_text", lambda prompt, key, r=reply: calls.append(prompt) or r)
        results.append(_score(path))
    assert results[0] == results[1]
    assert calls == []  # scorer.score_candidate never asks an LLM anything


@pytest.mark.parametrize("name", NAMES)
def test_score_delta_against_the_clean_twin(name):
    clean = _score(FIXTURES / "clean.txt")
    injected = _score(FIXTURES / f"injected_{name}.txt")
    assert clean.composite_score == CLEAN_COMPOSITE
    assert injected.composite_score - clean.composite_score == EXPECTED_DELTA[name]


def test_known_limit_keyword_stuffing_raises_the_skill_score():
    """Documented, not fixed: skill match counts listed keywords, so a pasted JD skill list scores as a match."""
    clean = _score(FIXTURES / "clean.txt")
    stuffed = _score(FIXTURES / "injected_keyword_stuffing.txt")
    assert (clean.skill_match_score, stuffed.skill_match_score) == (25.0, 100.0)
    assert stuffed.missing_skills == []


def test_screen_route_score_ignores_a_compliant_explanation(client, monkeypatch):  # noqa: F811
    """The explanation is written after scoring; its text cannot move the stored numbers."""
    job = make_job(client)
    data = (FIXTURES / "injected_score_claim.txt").read_bytes()
    candidate = client.post(f"/api/candidates?job_id={job['id']}", content_type="multipart/form-data",
                            data={"resume": (io.BytesIO(data), "score_claim.txt")}).get_json()
    monkeypatch.setattr(config, "get_api_key", lambda: "test-key")
    stored = {}
    for reply in (COMPLIANT, REFUSING):
        monkeypatch.setattr(llm, "generate_text", lambda prompt, key, r=reply: r)
        stored[reply] = screen(client, candidate["id"], job["id"]).get_json()
    numbers = ("composite_score", "semantic_score", "skill_match_score", "experience_score", "education_score")
    assert [stored[COMPLIANT][k] for k in numbers] == [stored[REFUSING][k] for k in numbers]
    assert stored[COMPLIANT]["composite_score"] == CLEAN_COMPOSITE
    # Limit: the explanation is stored verbatim, so a compliant model's "score: 100" reaches the recruiter.
    assert stored[COMPLIANT]["reasoning"] == COMPLIANT


ABSURD_PROFILE = {
    "name": "Priya Raman", "email": "", "phone": "",
    "skills": ["Machine Learning", "Python", "TensorFlow", "PyTorch", "Pandas", "NumPy", "Git", "GitHub"],
    "experience_years": 99, "education": [{"degree": "PhD", "field": "", "institution": ""}], "work_history": [],
}


@pytest.mark.parametrize("name", ["ignore_instructions", "score_claim", "skills_hidden"])
def test_compliant_llm_parser_cannot_change_the_score(name, monkeypatch):
    path = FIXTURES / f"injected_{name}.txt"
    regex_score = _score(path).composite_score
    monkeypatch.setattr(resume_parser, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(llm, "generate_text", lambda prompt, key: json.dumps(ABSURD_PROFILE))
    assert _score(path).composite_score == regex_score
