"""Edge cases, failure paths and races for POST /api/agent/run and POST /api/agent/approve/<thread_id>.

These go through the app and its database, so with TEST_DATABASE_URL they run on PostgreSQL
too. Every LLM here is a scripted fake; none reaches a real provider.

Tests marked xfail(strict=True) with a "BUG:" reason pin behavior that is wrong today. When the
bug is fixed they XPASS, which fails the suite, so the fix must remove the marker.
"""
import os
import sqlite3
import subprocess
import threading
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

import agent
import agent_llm
import agent_tools
import config
import scorer
import screening
from agent_tools import ScoreInput, ToolContext
from models import AgentShortlist, Candidate, Job, ScreeningResult
from tests import test_agent_api, test_api_contract
from tests.test_agent_api import run
from tests.test_api_contract import make_job, screen, upload
from tests.test_recruiting_agent import ScriptedLLM
from tests.test_retrieval import KeywordProvider

# Fixtures shared with the existing API tests (assigned, so parameters may reuse the names).
app_module, client, pool = test_api_contract.app_module, test_api_contract.client, test_agent_api.pool

ON_SQLITE = make_url(os.environ["DATABASE_URL"]).get_backend_name() == "sqlite"
APPROVE = {"decision": "approve", "reviewer": "Rita"}
NOT_WAITING = {"error": "No run is waiting for approval with this thread_id"}
GENERIC_500 = {"error": "Internal server error"}
ALREADY_DECIDED = {"error": "This run was already decided"}
SECRET = "secret-detail postgresql://hireai:pw@db.internal/hireai C:\\srv\\app.py"


def pending(api, job_id, request="Shortlist the top 2 Python engineers"):
    body = run(api, request, job_id=job_id).get_json()
    assert body["status"] == "pending_approval", body
    return body


def decide(api, thread, **body):
    return api.post(f"/api/agent/approve/{thread}", json={**APPROVE, **body})


def shortlists(app):
    with app.SessionLocal() as session:
        rows = session.query(AgentShortlist).order_by(AgentShortlist.id)
        return [(r.thread_id, r.job_id, r.approved_by) for r in rows]


def use_llm(monkeypatch, fake):
    """Make /api/agent/run plan with a scripted fake instead of a configured provider."""
    monkeypatch.setattr(agent_llm, "get_provider", lambda: fake)
    return fake


# --- malformed and oversized requests ---------------------------------------------------------
@pytest.mark.parametrize("kwargs", [
    {},                                                                    # no body at all
    {"data": "{not json", "content_type": "application/json"},
    {"data": "request=Who+knows+Python", "content_type": "application/x-www-form-urlencoded"},
    {"json": ["Who knows Python?"]},
    {"json": "Who knows Python?"},
    {"json": {"request": ["Who knows Python?"]}},
    {"json": {"request": {"text": "Who knows Python?"}}},
    {"json": {"request": None}},
    {"json": {"request": "\n\t  \r\n"}},
    {"json": {"request": "ok", "job_id": 1.0}},
    {"json": {"request": "ok", "job_id": [1]}},
    {"json": {"request": "ok", "job_id": False}},
    {"json": {"request": "ok", "job_id": "one"}},
], ids=lambda kw: repr(kw)[:40])
def test_malformed_run_requests_are_400(pool, kwargs):
    api, _, _ = pool
    response = api.post("/api/agent/run", **kwargs)
    assert response.status_code == 400
    assert set(response.get_json()) == {"error"}


def test_run_request_limit_counts_normalized_text(pool):
    api, _, _ = pool
    assert run(api, "x" * agent.MAX_REQUEST_CHARS).status_code == 200            # the limit is inclusive
    assert run(api, "Who" + " " * 2000 + "knows Python?").status_code == 200    # whitespace runs collapse
    assert run(api, "x" * (agent.MAX_REQUEST_CHARS + 1)).status_code == 400


@pytest.mark.parametrize("job_id", [0, -1])
def test_non_positive_job_id_is_not_found(pool, job_id):
    api, _, _ = pool
    assert run(api, "shortlist python", job_id=job_id).status_code == 404


def test_oversized_bodies_are_413_before_anything_runs(pool, monkeypatch):
    api, job_id, app = pool
    thread = pending(api, job_id)["thread_id"]
    monkeypatch.setattr(agent, "start_run", lambda *a, **k: pytest.fail("ran an oversized request"))
    big = "y" * (app.AGENT_MAX_BODY_BYTES + 1)
    assert api.post("/api/agent/run", json={"request": "x", "pad": big}).status_code == 413
    assert api.post(f"/api/agent/approve/{thread}", json={**APPROVE, "note": big}).status_code == 413
    assert agent.is_pending(app.agent_checkpointer(), thread) and shortlists(app) == []


# SQLite holds 64-bit integers; PostgreSQL's INTEGER columns stop at 2**31 - 1.
BIG_IDS = [pytest.param(2**31, id="2**31"), pytest.param(2**63, id="2**63")]


@pytest.mark.parametrize("big", BIG_IDS)
def test_out_of_range_job_id_is_a_client_error(pool, big):
    api, _, _ = pool
    response = run(api, "shortlist python", job_id=big)
    assert response.status_code in (400, 404)


@pytest.mark.parametrize("big", BIG_IDS)
def test_out_of_range_candidate_id_in_a_request_is_a_failed_step_not_a_500(pool, big):
    api, job_id, _ = pool
    response = run(api, f"Score candidate {big} for job {job_id}")
    assert response.status_code == 200
    step = response.get_json()["steps"][0]
    assert step["tool"] == "score_candidate" and step["ok"] is False


@pytest.mark.parametrize("kwargs", [
    {},
    {"data": "{not json", "content_type": "application/json"},
    {"json": ["approve", "Rita"]},
    {"json": {"decision": "approve", "reviewer": 7}},
    {"json": {"decision": "approve", "reviewer": ["Rita"]}},
    {"json": {"decision": "approve", "reviewer": None}},
    {"json": {"decision": "approve", "reviewer": True}},
    {"json": {"decision": "approve", "reviewer": {"name": "Rita"}}},
    {"json": {"decision": "approve", "reviewer": " \t "}},
    {"json": {"decision": "approve", "reviewer": "r" * 256}},
    {"json": {"decision": "APPROVE", "reviewer": "Rita"}},
    {"json": {"decision": True, "reviewer": "Rita"}},
    {"json": {"decision": ["approve"], "reviewer": "Rita"}},
    {"json": {"decision": "approve", "reviewer": "Rita", "note": "n" * 2001}},
    {"json": {"decision": "approve", "reviewer": "Rita", "note": ["fine"]}},
], ids=lambda kw: repr(kw)[:40])
def test_malformed_decisions_are_400_and_leave_the_run_pending(pool, kwargs):
    api, job_id, app = pool
    thread = pending(api, job_id)["thread_id"]
    response = api.post(f"/api/agent/approve/{thread}", **kwargs)
    assert response.status_code == 400
    assert set(response.get_json()) == {"error"}
    assert agent.is_pending(app.agent_checkpointer(), thread) and shortlists(app) == []


def test_approval_records_the_stripped_reviewer_and_the_time(pool):
    api, job_id, app = pool
    thread = pending(api, job_id)["thread_id"]
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    reviewer = "r" * 255  # the limits are inclusive, and checked after stripping
    response = decide(api, thread, reviewer=f"  {reviewer}\n", note="n" * 2000, ignored="extra keys are dropped")
    after = datetime.now(timezone.utc).replace(tzinfo=None)
    assert response.status_code == 200
    saved = response.get_json()["shortlist"]
    assert (saved["approved_by"], saved["note"], saved["thread_id"]) == (reviewer, "n" * 2000, thread)
    assert before <= datetime.fromisoformat(saved["approved_at"]) <= after
    assert shortlists(app) == [(thread, job_id, reviewer)]


# --- unknown, expired and already-decided threads -----------------------------------------------
@pytest.mark.parametrize("thread", ["0" * 64, "ab.cd", "ab%20cd", "ab~cd", "ab%00cd", "a" * 65])
def test_unknown_or_malformed_thread_ids_are_404(pool, thread):
    api, _, _ = pool
    response = decide(api, thread)
    assert (response.status_code, response.get_json()) == (404, NOT_WAITING)


def test_threads_that_never_paused_cannot_be_approved(pool, monkeypatch):
    api, job_id, app = pool
    answered = run(api, "Who knows Python?").get_json()
    asked = run(api, "Score this candidate").get_json()                 # rule-based "please name ..."
    use_llm(monkeypatch, ScriptedLLM("not json"))
    stopped = run(api, "Shortlist the best", job_id=job_id).get_json()
    assert [b["status"] for b in (answered, asked, stopped)] == ["answered", "answered", "stopped"]
    for body in (answered, asked, stopped):
        response = decide(api, body["thread_id"])
        assert (response.status_code, response.get_json()) == (404, NOT_WAITING)
    assert shortlists(app) == []


def test_thread_lost_with_its_checkpoint_file_is_404(pool, monkeypatch, tmp_path):
    """An expired thread: the app restarted with a new AGENT_CHECKPOINT_DB, so the pause is gone."""
    api, job_id, app = pool
    old = pending(api, job_id)["thread_id"]
    monkeypatch.setattr(app, "_agent_checkpointer", None)
    monkeypatch.setenv("AGENT_CHECKPOINT_DB", str(tmp_path / "fresh.db"))
    assert (decide(api, old).status_code, shortlists(app)) == (404, [])
    new = pending(api, job_id)["thread_id"]
    assert decide(api, new).status_code == 200


def test_approve_twice_keeps_the_first_reviewer(pool):
    api, job_id, app = pool
    thread = pending(api, job_id)["thread_id"]
    assert decide(api, thread, reviewer="Rita").status_code == 200
    for again in ({"reviewer": "Mallory"}, {"decision": "reject", "reviewer": "Mallory"}):
        response = decide(api, thread, **again)
        assert (response.status_code, response.get_json()) == (409, ALREADY_DECIDED)
    assert shortlists(app) == [(thread, job_id, "Rita")]


def test_reject_then_reject_or_approve_is_409(pool):
    api, job_id, app = pool
    thread = pending(api, job_id)["thread_id"]
    first = decide(api, thread, decision="reject")
    assert (first.status_code, first.get_json()["status"], first.get_json()["shortlist"]) == (200, "rejected", None)
    for again in ("reject", "approve"):
        response = decide(api, thread, decision=again)
        assert (response.status_code, response.get_json()) == (409, ALREADY_DECIDED)
    assert shortlists(app) == []


def _race(app, thread, decisions, monkeypatch):
    """Send the decisions at once. Each request waits after its pending check until the other has
    made its own check, so both arrive while the run is still paused (a deterministic race)."""
    barrier = threading.Barrier(len(decisions))
    real = agent.is_pending

    def racing_is_pending(checkpointer, thread_id):
        result = real(checkpointer, thread_id)
        try:
            barrier.wait(timeout=3)
        except threading.BrokenBarrierError:  # e.g. a fix that serializes the check
            pass
        return result

    monkeypatch.setattr(agent, "is_pending", racing_is_pending)
    responses = []

    def send(decision):
        response = app.app.test_client().post(f"/api/agent/approve/{thread}",
                                              json={"decision": decision, "reviewer": decision})
        responses.append((decision, response.status_code, response.get_json()))

    workers = [threading.Thread(target=send, args=(d,)) for d in decisions]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=60)
    return responses


@pytest.mark.parametrize("decisions", [("approve", "approve"), ("approve", "reject")])
def test_concurrent_decisions_on_one_thread_exactly_one_wins(pool, monkeypatch, decisions):
    api, job_id, app = pool
    thread = pending(api, job_id)["thread_id"]
    responses = _race(app, thread, decisions, monkeypatch)
    assert sorted(code for _, code, _ in responses) in ([200, 404], [200, 409]), responses
    winner = next(d for d, code, _ in responses if code == 200)
    assert len(shortlists(app)) == (1 if winner == "approve" else 0)


# --- data changing between proposal and approval -------------------------------------------------
def test_job_deleted_before_approval_is_refused_cleanly(pool):
    api, job_id, app = pool
    thread = pending(api, job_id)["thread_id"]
    assert api.delete(f"/api/jobs/{job_id}").status_code == 200
    response = decide(api, thread)
    assert response.status_code in (404, 409, 410), response.get_json()
    assert set(response.get_json()) == {"error"}
    assert shortlists(app) == []


def test_candidate_deleted_before_approval_is_not_in_the_saved_shortlist(pool):
    api, job_id, app = pool
    body = pending(api, job_id)
    gone = body["proposal"]["entries"][0]["candidate_id"]
    assert api.delete(f"/api/candidates/{gone}").status_code == 200
    response = decide(api, body["thread_id"])
    if response.status_code == 200:  # either drop the deleted candidate, or refuse the approval
        assert gone not in [e["candidate_id"] for e in response.get_json()["shortlist"]["entries"]]
    else:
        assert response.status_code in (404, 409, 410) and shortlists(app) == []


# --- providers and planners failing ---------------------------------------------------------------
def test_unknown_provider_name_is_a_generic_503(pool, monkeypatch):
    api, _, _ = pool
    monkeypatch.setenv("AGENT_LLM_ENABLED", "true")
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "mystery-llm")
    response = run(api, "Who knows Python?")
    assert (response.status_code, response.get_json()) == (503, {"error": "The agent's LLM provider is not available"})


def test_provider_raising_mid_run_ends_it_with_a_generic_message(pool, monkeypatch):
    api, job_id, app = pool
    calls = []

    class Flaky:
        name = "flaky"

        def generate(self, prompt):
            calls.append(prompt)
            if len(calls) == 1:
                return '{"action": "call_tool", "tool": "search_candidates", "args": {"query": "Python"}}'
            raise RuntimeError(SECRET)

    use_llm(monkeypatch, Flaky())
    response = run(api, "Shortlist the best Python engineers", job_id=job_id)
    body = response.get_json()
    assert (response.status_code, body["status"], len(calls)) == (200, "error", 2)
    assert [s["tool"] for s in body["steps"]] == ["search_candidates"] and body["steps"][0]["ok"]
    assert "secret" not in response.get_data(as_text=True)
    assert decide(api, body["thread_id"]).status_code == 404 and shortlists(app) == []


def test_planner_returning_invalid_json_every_time_stops_at_the_turn_cap(pool, monkeypatch):
    api, job_id, _ = pool
    fake = use_llm(monkeypatch, ScriptedLLM("Sure! First I will search for Python people.", "{'action': 'finish'}",
                                            '{"action": "finish"', "null"))
    body = run(api, "Shortlist the best", job_id=job_id).get_json()
    assert body["status"] == "stopped" and len(fake.prompts) == agent.MAX_TURNS
    assert len(body["steps"]) == agent.MAX_TURNS and {s["type"] for s in body["steps"]} == {"refused"}
    assert decide(api, body["thread_id"]).status_code == 404


def test_tool_cap_through_the_api(pool, monkeypatch):
    api, job_id, _ = pool
    fake = use_llm(monkeypatch, ScriptedLLM({"action": "call_tool", "tool": "search_candidates",
                                             "args": {"query": "Python", "job_id": job_id}}))
    body = run(api, "Shortlist the best", job_id=job_id).get_json()
    assert body["status"] == "stopped" and body["proposal"] is None
    assert len(fake.prompts) == len(body["steps"]) == agent.MAX_TOOL_CALLS + 1  # the last reply is refused


def test_unexpected_errors_are_generic(pool, monkeypatch):
    api, job_id, _ = pool
    thread = pending(api, job_id)["thread_id"]

    def boom(*args, **kwargs):
        raise RuntimeError(SECRET)

    for target in ("start_run", "resume_run"):
        monkeypatch.setattr(agent, target, boom)
    run_response, approve_response = run(api, "Who knows Python?"), decide(api, thread)
    monkeypatch.setattr(agent_llm, "get_provider", boom)  # raised outside the route's try block
    provider_response = run(api, "Who knows Python?")
    for response in (run_response, approve_response, provider_response):
        assert (response.status_code, response.get_json()) == (500, GENERIC_500)
        assert "secret" not in response.get_data(as_text=True)


# --- empty pool -----------------------------------------------------------------------------------
def test_empty_candidate_pool_proposes_nothing(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module.embeddings, "get_provider", lambda: KeywordProvider())
    job_id = make_job(client)["id"]
    body = run(client, "Shortlist the top 3 Python engineers", job_id=job_id).get_json()
    assert (body["status"], body["proposal"]) == ("answered", None)
    assert body["steps"][0]["result"]["hits"] == [] and "no shortlist" in body["message"]
    use_llm(monkeypatch, ScriptedLLM({"action": "propose_shortlist", "candidate_ids": [1, 2, 3]}))
    invented = run(client, "Shortlist anyone", job_id=job_id).get_json()
    assert (invented["status"], invented["proposal"]) == ("answered", None)
    for thread in (body["thread_id"], invented["thread_id"]):
        assert decide(client, thread).status_code == 404
    assert shortlists(app_module) == []


# --- the checkpoint database ----------------------------------------------------------------------
def test_checkpoints_are_written_to_AGENT_CHECKPOINT_DB(pool, monkeypatch, tmp_path):
    api, job_id, app = pool
    path = tmp_path / "paused-runs.db"
    monkeypatch.setattr(app, "_agent_checkpointer", None)
    monkeypatch.setenv("AGENT_CHECKPOINT_DB", str(path))
    thread = pending(api, job_id)["thread_id"]
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (thread,)).fetchone()[0] > 0
    finally:
        conn.close()
    assert app.agent_checkpointer() is app.agent_checkpointer()  # one saver per process


def test_default_checkpoint_db_is_git_ignored(app_module):
    default = app_module.DEFAULT_AGENT_CHECKPOINT_DB
    assert os.path.dirname(default) == os.path.dirname(os.path.abspath(app_module.__file__))
    try:
        ignored = subprocess.run(["git", "check-ignore", "-q", default], cwd=os.path.dirname(default),
                                 capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("git is not available")
    if ignored.returncode == 128:
        pytest.skip("not a git checkout")
    assert ignored.returncode == 0, "agent_checkpoints.db holds resume passages and must stay out of git"


def test_unusable_checkpoint_path_is_a_generic_500_and_recovers(pool, monkeypatch, tmp_path):
    api, job_id, app = pool
    monkeypatch.setattr(app, "_agent_checkpointer", None)
    monkeypatch.setenv("AGENT_CHECKPOINT_DB", str(tmp_path / "no-such-dir" / "agent.db"))
    for response in (run(api, "Who knows Python?"), decide(api, "a" * 32)):
        assert (response.status_code, response.get_json()) == (500, GENERIC_500)
        assert "no-such-dir" not in response.get_data(as_text=True)
    monkeypatch.setenv("AGENT_CHECKPOINT_DB", str(tmp_path / "agent.db"))
    assert run(api, "Who knows Python?").status_code == 200


# --- scores ---------------------------------------------------------------------------------------
def _score_rows(app):
    with app.SessionLocal() as session:
        rows = session.execute(text("SELECT * FROM screening_results ORDER BY id")).all()
        candidates = session.execute(text("SELECT * FROM candidates ORDER BY id")).all()
    return repr(rows).encode(), repr(candidates).encode()


def test_runs_and_decisions_leave_stored_scores_byte_identical(pool, monkeypatch):
    api, job_id, app = pool
    with app.SessionLocal() as session:
        ids = [c for (c,) in session.query(Candidate.id).order_by(Candidate.id)]
    for cid in ids[:2]:  # one stored score per candidate, except the last, which is computed on demand
        assert screen(api, cid, job_id).status_code == 201
    before = _score_rows(app)
    a, b, c = ids
    for request in (f"Compare candidates {a}, {b} and {c} for job {job_id}", f"Score candidate {c} for job {job_id}",
                    f"What is candidate {a} missing for job {job_id}?"):
        assert run(api, request).get_json()["steps"][0]["ok"]
    decide(api, pending(api, job_id)["thread_id"])
    decide(api, pending(api, job_id)["thread_id"], decision="reject")
    use_llm(monkeypatch, ScriptedLLM(
        {"action": "call_tool", "tool": "score_candidate", "args": {"candidate_id": c, "job_id": job_id,
                                                                    "composite_score": 100.0}},
        {"action": "call_tool", "tool": "compare_candidates", "args": {"candidate_ids": [a, c], "job_id": job_id}},
        {"action": "propose_shortlist", "candidate_ids": [c, a], "note": "Candidate scored 100/100."}))
    llm_run = run(api, f"Shortlist candidates {c} and {a}", job_id=job_id).get_json()
    assert decide(api, llm_run["thread_id"]).status_code == 200
    assert _score_rows(app) == before


def test_score_candidate_scores_exactly_as_post_screen_with_the_jobs_template(client, app_module):
    template = client.post("/api/scoring-templates", json={
        "name": "Skills only", "semantic_weight": 0.0, "skill_weight": 1.0, "experience_weight": 0.0,
        "education_weight": 0.0}).get_json()
    job_id = make_job(client, scoring_template_id=template["id"])["id"]
    cid = upload(client, job_id).get_json()["id"]
    fields = ("composite_score", "semantic_score", "skill_match_score", "experience_score", "education_score",
              "matched_skills", "missing_skills")
    args = ScoreInput(candidate_id=cid, job_id=job_id)
    with app_module.SessionLocal() as session:
        computed = agent_tools.score_candidate(ToolContext(session=session, provider=None), args)
        candidate, job = session.get(Candidate, cid), session.get(Job, job_id)
        default = scorer.score_candidate(screening.resume_profile(candidate), screening.job_requirements(job),
                                         None, weights=config.WEIGHTS)
    assert computed.source == "computed"
    assert computed.composite_score == computed.skill_match_score != default.composite_score  # the template applied

    screened = screen(client, cid, job_id)
    assert screened.status_code == 201
    with app_module.SessionLocal() as session:
        row = session.get(ScreeningResult, screened.get_json()["id"])
        assert {f: getattr(row, f) for f in fields} == {f: getattr(computed, f) for f in fields}
        stored = agent_tools.score_candidate(ToolContext(session=session, provider=None), args)
    assert (stored.source, stored.screening_id) == ("stored", row.id)
    assert {f: getattr(stored, f) for f in fields} == {f: getattr(computed, f) for f in fields}
