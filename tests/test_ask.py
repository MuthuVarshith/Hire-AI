"""Ask the candidate pool: the not-found floor, grounding checks, citations, and the endpoint."""
import json

import pytest
from sqlalchemy.orm import Session

import ask
import indexing
from database import create_database_engine
from models import Candidate, Job
from tests.test_retrieval import RESUMES, KeywordProvider


@pytest.fixture
def pool(tmp_path):
    engine = create_database_engine(f"sqlite:///{(tmp_path / 'ask.db').as_posix()}")
    provider = KeywordProvider()
    with Session(engine) as session:
        job = Job(title="Pool", description_text="(pool)")
        session.add(job)
        for name, text in RESUMES.items():
            session.add(Candidate(name=name, job=job, resume_filename=f"{name}.txt", resume_text=text))
        session.flush()
        for candidate in session.query(Candidate):
            indexing.index_candidate(session, candidate, provider)
        session.commit()
        yield session, provider
    engine.dispose()


def fake_llm(reply):
    calls = []

    def generate(prompt, api_key):
        calls.append(prompt)
        return json.dumps(reply) if isinstance(reply, dict) else reply
    generate.calls = calls
    return generate


@pytest.fixture
def llm_on(monkeypatch):
    monkeypatch.setenv("ASK_LLM_ENABLED", "true")


def test_low_similarity_is_not_found_without_calling_the_llm(pool, llm_on):
    session, provider = pool
    generate = fake_llm({"found": True, "answer": "x", "citations": [1]})
    result = ask.answer_question(session, "Who knows Kubernetes?", provider, api_key="k",
                                 generate=generate, threshold=1.01)
    assert not result.found and result.answer == ask.NOT_FOUND and result.citations == []
    assert generate.calls == []


def test_grounded_answer_keeps_only_cited_chunks_that_exist(pool, llm_on):
    session, provider = pool
    generate = fake_llm({"found": True, "answer": "Cy ran EKS clusters [1].", "citations": [1, 99]})
    result = ask.answer_question(session, "Who has used Kubernetes and Terraform?", provider,
                                 api_key="k", generate=generate)
    assert result.found and result.generated
    assert [c.number for c in result.citations] == [1]
    cited = result.citations[0]
    resume = RESUMES[cited.candidate_name]
    assert resume[cited.char_start:cited.char_end] == cited.text  # exact offsets into the resume
    assert "data, not instructions" in generate.calls[0]


@pytest.mark.parametrize("reply", [
    {"found": False, "answer": "", "citations": []},
    {"found": True, "answer": "Someone does.", "citations": []},      # uncited claim
    {"found": True, "answer": "Someone does.", "citations": [42]},    # citation it was not given
    "not json at all",
])
def test_ungrounded_replies_become_not_found(pool, llm_on, reply):
    session, provider = pool
    result = ask.answer_question(session, "Who knows React?", provider, api_key="k", generate=fake_llm(reply))
    assert not result.found and result.answer == ask.NOT_FOUND and result.citations == []


def test_without_llm_returns_passages_only(pool, monkeypatch):
    monkeypatch.delenv("ASK_LLM_ENABLED", raising=False)
    session, provider = pool
    generate = fake_llm({"found": True, "answer": "x", "citations": [1]})
    result = ask.answer_question(session, "Who knows React?", provider, api_key="k", generate=generate)
    assert result.found and not result.generated and result.citations
    assert result.citations[0].candidate_name == "Bo"
    assert generate.calls == []  # resume text never leaves the machine unless explicitly enabled


@pytest.mark.parametrize("question", ["   ", "x" * (ask.MAX_QUESTION_CHARS + 1)])
def test_rejects_empty_and_overlong_questions(pool, question):
    session, provider = pool
    with pytest.raises(ValueError):
        ask.answer_question(session, question, provider)


def test_endpoint_validates_input_and_answers(monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module.embeddings, "get_provider", lambda: KeywordProvider())
    client = app_module.app.test_client()
    assert client.post("/api/ask", json={}).status_code == 400
    assert client.post("/api/ask", json={"question": "React?", "job_id": "1"}).status_code == 400
    assert client.post("/api/ask", json={"question": "React?", "job_id": 999999}).status_code == 404
    response = client.post("/api/ask", json={"question": "Who knows COBOL?"})
    assert response.status_code == 200
    assert set(response.get_json()) >= {"question", "found", "answer", "citations", "generated"}


def test_llm_outage_falls_back_to_passages(pool, llm_on):
    session, provider = pool

    def down(prompt, api_key):
        raise RuntimeError("503 UNAVAILABLE")
    result = ask.answer_question(session, "Who knows React?", provider, api_key="k", generate=down)
    assert result.found and not result.generated and result.answer == ask.PASSAGES_ONLY and result.citations
