"""POST /api/agent/run and POST /api/agent/approve/<thread_id>: the rule-based agent end to end."""
import pytest

import agent_llm
from models import AgentShortlist
from tests.test_api_contract import app_module, client, make_job, upload  # noqa: F401  (fixtures)
from tests.test_retrieval import KeywordProvider

RESUMES = ("resume_01_ananya_patel.txt", "resume_02_michael_chen.txt", "resume_03_sophia_nguyen.txt")


@pytest.fixture
def pool(client, app_module, monkeypatch):  # noqa: F811
    """(test client, job id, app module) with three sample resumes uploaded and indexed."""
    monkeypatch.setattr(app_module.embeddings, "get_provider", lambda: KeywordProvider())
    job = make_job(client)
    for name in RESUMES:
        assert upload(client, job["id"], name).status_code == 201
    return client, job["id"], app_module


APPROVE = {"decision": "approve", "reviewer": "Rita"}


def run(api, request, **body):
    return api.post("/api/agent/run", json={"request": request, **body})


def test_shortlist_waits_for_approval_and_records_the_reviewer(pool):
    api, job_id, app = pool
    response = run(api, "Shortlist the top 2 Python engineers", job_id=job_id)
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "pending_approval" and body["shortlist"] is None
    entries = body["proposal"]["entries"]
    assert 1 <= len(entries) <= 2 and all("composite_score" in e and "citations" in e for e in entries)
    with app.SessionLocal() as session:
        assert session.query(AgentShortlist).count() == 0

    url = f"/api/agent/approve/{body['thread_id']}"
    approved = api.post(url, json={"decision": "approve", "reviewer": "Rita", "note": "ok"})
    assert approved.status_code == 200
    shortlist = approved.get_json()["shortlist"]
    assert (shortlist["approved_by"], shortlist["note"], shortlist["job_id"]) == ("Rita", "ok", job_id)
    assert shortlist["entries"] == entries and shortlist["approved_at"]
    again = api.post(url, json={"decision": "reject", "reviewer": "Rita"})
    assert (again.status_code, again.get_json()) == (409, {"error": "This run was already decided"})


def test_rejected_runs_save_nothing_and_cannot_be_decided_twice(pool):
    api, job_id, app = pool
    thread = run(api, "shortlist python", job_id=job_id).get_json()["thread_id"]
    url = f"/api/agent/approve/{thread}"
    assert api.post(url, json={"decision": "reject", "reviewer": "Rita"}).get_json()["status"] == "rejected"
    assert api.post(url, json={"decision": "approve", "reviewer": "Rita"}).status_code == 409
    with app.SessionLocal() as session:
        assert session.query(AgentShortlist).count() == 0


def test_answers_without_a_shortlist(pool):
    api, _, _ = pool
    body = run(api, "Who knows Python?").get_json()
    assert body["status"] == "answered" and body["proposal"] is None
    assert body["steps"][0]["tool"] == "search_candidates"


@pytest.mark.parametrize("body,status", [
    ({}, 400),
    ({"request": "   "}, 400),
    ({"request": "x" * 501}, 400),
    ({"request": "ok", "job_id": True}, 400),
    ({"request": "ok", "job_id": "1"}, 400),
    ({"request": "ok", "job_id": 999}, 404),
])
def test_run_validation(pool, body, status):
    api, _, _ = pool
    assert api.post("/api/agent/run", json=body).status_code == status


@pytest.mark.parametrize("body", [
    {}, {"decision": "approve"}, {"decision": "maybe", "reviewer": "r"},
    {"decision": "approve", "reviewer": "r", "note": 5}, {"decision": "approve", "reviewer": ""},
])
def test_approve_validation(pool, body):
    api, job_id, _ = pool
    thread = run(api, "shortlist python", job_id=job_id).get_json()["thread_id"]
    assert api.post(f"/api/agent/approve/{thread}", json=body).status_code == 400
    assert api.post(f"/api/agent/approve/{thread}",  # still pending after a bad request
                       json={"decision": "approve", "reviewer": "r"}).status_code == 200


def test_unknown_thread_is_404(pool):
    api, _, _ = pool
    for thread in ("does-not-exist", "x" * 65):
        response = api.post(f"/api/agent/approve/{thread}", json={"decision": "approve", "reviewer": "r"})
        assert response.status_code == 404


def test_misconfigured_provider_is_a_generic_503(pool, monkeypatch):
    api, _, _ = pool
    monkeypatch.setenv("AGENT_LLM_ENABLED", "true")
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "openai")

    def missing(name):
        raise ImportError(name)
    monkeypatch.setattr(agent_llm.importlib, "import_module", missing)
    response = run(api, "Who knows Python?")
    assert (response.status_code, response.get_json()) == (503, {"error": "The agent's LLM provider is not available"})


def test_large_bodies_are_rejected(pool):
    api, _, _ = pool
    big = {"request": "x", "pad": "y" * 20000}
    assert api.post("/api/agent/run", json=big).status_code == 413
    assert api.post("/api/agent/approve/abc", json=big).status_code == 413


def test_agent_endpoints_send_no_cors_headers_but_others_still_do(pool):
    api, job_id, _ = pool
    origin = {"Origin": "https://attacker.example"}
    for url in ("/api/agent/run", "/api/agent/approve/abc"):
        preflight = api.options(url, headers={**origin, "Access-Control-Request-Method": "POST",
                                              "Access-Control-Request-Headers": "Content-Type"})
        assert "Access-Control-Allow-Origin" not in preflight.headers
        posted = api.post(url, json={"request": "Who knows Python?", **APPROVE}, headers=origin)
        assert "Access-Control-Allow-Origin" not in posted.headers
    assert api.get("/api/jobs", headers=origin).headers.get("Access-Control-Allow-Origin")  # other routes keep CORS


@pytest.mark.parametrize("content_type", ["application/x-www-form-urlencoded", "multipart/form-data", "text/plain"])
def test_agent_endpoints_accept_only_json_bodies(pool, content_type):
    api, job_id, app = pool
    thread = run(api, "shortlist python", job_id=job_id).get_json()["thread_id"]
    form = api.post("/api/agent/run", data="request=Who+knows+Python", content_type=content_type)
    approve = api.post(f"/api/agent/approve/{thread}", data="decision=approve&reviewer=x", content_type=content_type)
    for response in (form, approve):
        assert response.status_code == 400
        assert response.get_json() == {"error": "Content-Type must be application/json"}
    with app.SessionLocal() as session:
        assert session.query(AgentShortlist).count() == 0
