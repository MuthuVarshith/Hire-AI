"""The LangGraph agent: rule-based and mocked-LLM runs, the approval interrupt, the checkpointer,
the providers, and a check that no run changes a stored score.

Every LLM here is a scripted fake; none reaches a real provider.
"""
import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import text
from sqlalchemy.orm import Session

import agent
import agent_llm
import config
import llm
from agent_tools import ToolContext
from database import create_database_engine
from models import AgentShortlist
from tests.test_agent_tools import make_pool, no_model  # noqa: F401  (fixture)
from tests.test_retrieval import KeywordProvider


@pytest.fixture
def env(tmp_path, no_model):  # noqa: F811
    engine = create_database_engine(f"sqlite:///{(tmp_path / 'agent.db').as_posix()}")
    provider = KeywordProvider()
    with Session(engine) as session:
        ids = make_pool(session, provider)
        yield ToolContext(session=session, provider=provider), ids, InMemorySaver()
    engine.dispose()


class ScriptedLLM:
    """A fake planner LLM that replies from a script and records every prompt it was sent.
    A reply may be a function of the prompt; the last reply repeats once the script runs out."""

    name = "scripted"

    def __init__(self, *replies):
        self.replies = replies
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        reply = self.replies[min(len(self.prompts), len(self.replies)) - 1]
        reply = reply(prompt) if callable(reply) else reply
        return reply if isinstance(reply, str) else json.dumps(reply)


def run(ctx, saver, request, planner=agent.rule_based_planner, job_id=None):
    return agent.start_run(ctx, request, planner, saver, job_id=job_id)


def approve(ctx, saver, result, decision="approve", reviewer="Rita Recruiter", note=None):
    return agent.resume_run(ctx, result["thread_id"], {"decision": decision, "reviewer": reviewer, "note": note},
                            agent.rule_based_planner, saver)


# --- rule-based router ------------------------------------------------------------------
def test_rule_based_search_answers_without_a_shortlist(env):
    ctx, ids, saver = env
    result = run(ctx, saver, "Who has run Kubernetes clusters?")
    assert result["status"] == "answered" and result["proposal"] is None
    assert [s["tool"] for s in result["steps"]] == ["search_candidates"]
    assert result["message"].startswith("Found ")


@pytest.mark.parametrize("request_text,tool", [
    ("Show the profile of candidate {Cy}", "get_candidate_profile"),
    ("Score candidate {Cy} for job {backend}", "score_candidate"),
    ("Compare candidates {Ada} and {Cy} for job {backend}", "compare_candidates"),
    ("What skills is candidate {Bo} missing for job {backend}?", "skill_gap_report"),
])
def test_rule_based_intents_route_to_the_tools(env, request_text, tool):
    ctx, ids, saver = env
    result = run(ctx, saver, request_text.format(**ids))
    assert [s["tool"] for s in result["steps"]] == [tool]
    assert result["steps"][0]["ok"] and result["status"] == "answered"


def test_rule_based_asks_for_missing_ids_instead_of_guessing(env):
    ctx, _, saver = env
    result = run(ctx, saver, "Score this candidate")
    assert result["steps"] == [] and "Please name" in result["message"]


def test_shortlist_pauses_for_approval_then_saves_with_reviewer(env):
    ctx, ids, saver = env
    result = run(ctx, saver, "Shortlist the top 2 candidates with Python and Docker", job_id=ids["backend"])
    assert result["status"] == "pending_approval" and result["shortlist"] is None
    assert ctx.session.query(AgentShortlist).count() == 0  # nothing exists before approval
    entries = result["proposal"]["entries"]
    assert len(entries) == 2
    assert [e["composite_score"] for e in entries] == sorted((e["composite_score"] for e in entries), reverse=True)
    assert all(e["citations"] for e in entries)
    assert agent.is_pending(saver, result["thread_id"])

    done = approve(ctx, saver, result, note="Looks right")
    assert done["status"] == "approved"
    row = ctx.session.query(AgentShortlist).one()
    assert (row.thread_id, row.approved_by, row.note, row.job_id) == (
        result["thread_id"], "Rita Recruiter", "Looks right", ids["backend"])
    assert row.approved_at is not None and row.entries == entries
    assert done["shortlist"]["id"] == row.id
    with pytest.raises(LookupError):  # a run is decided once
        approve(ctx, saver, result)


def test_rejection_saves_nothing(env):
    ctx, ids, saver = env
    result = run(ctx, saver, "shortlist backend engineers", job_id=ids["backend"])
    done = approve(ctx, saver, result, decision="reject")
    assert done["status"] == "rejected" and done["shortlist"] is None
    assert ctx.session.query(AgentShortlist).count() == 0


@pytest.mark.parametrize("decision", [
    {"decision": "yes", "reviewer": "r"},
    {"decision": "approve", "reviewer": "  "},
    {"decision": "approve"},
    {"decision": "approve", "reviewer": "r", "score": 100},
])
def test_invalid_decisions_leave_the_run_paused(env, decision):
    ctx, ids, saver = env
    result = run(ctx, saver, "shortlist python engineers", job_id=ids["backend"])
    with pytest.raises(ValueError):
        agent.resume_run(ctx, result["thread_id"], decision, agent.rule_based_planner, saver)
    assert agent.is_pending(saver, result["thread_id"])


def test_unknown_thread_cannot_be_resumed(env):
    ctx, _, saver = env
    with pytest.raises(LookupError):
        agent.resume_run(ctx, "no-such-thread", {"decision": "approve", "reviewer": "r"},
                         agent.rule_based_planner, saver)


def test_a_paused_run_survives_a_restart_with_the_sqlite_checkpointer(env, tmp_path):
    ctx, ids, _ = env
    path = str(tmp_path / "checkpoints.db")
    result = run(ctx, agent.sqlite_checkpointer(path), "shortlist python engineers", job_id=ids["backend"])
    reopened = agent.sqlite_checkpointer(path)  # a new connection, as after an app restart
    assert agent.is_pending(reopened, result["thread_id"])
    assert approve(ctx, reopened, result)["status"] == "approved"


@pytest.mark.parametrize("request_text,error", [("", "empty"), ("x" * 501, "longer"), (5, "string")])
def test_request_validation(env, request_text, error):
    ctx, _, saver = env
    with pytest.raises(ValueError, match=error):
        run(ctx, saver, request_text)
    with pytest.raises(ValueError, match="job_id"):
        run(ctx, saver, "ok", job_id=True)


# --- no run changes a score ---------------------------------------------------------------
def _score_rows(session):
    rows = session.execute(text("SELECT * FROM screening_results ORDER BY id")).all()
    candidates = session.execute(text("SELECT * FROM candidates ORDER BY id")).all()
    return repr(rows).encode(), repr(candidates).encode()


def test_scores_in_the_database_are_byte_identical_after_agent_runs(env):
    ctx, ids, saver = env
    before = _score_rows(ctx.session)
    for request in (f"Compare candidates {ids['Ada']}, {ids['Bo']} and {ids['Cy']} for job {ids['backend']}",
                    f"Score candidate {ids['Cy']} for job {ids['backend']}",
                    f"What is candidate {ids['Bo']} missing for job {ids['backend']}"):
        run(ctx, saver, request)
    llm_run = run(ctx, saver, "shortlist", job_id=ids["backend"], planner=agent.LLMPlanner(ScriptedLLM(
        {"action": "call_tool", "tool": "search_candidates", "args": {"query": "python kubernetes"}},
        {"action": "call_tool", "tool": "score_candidate",
         "args": {"candidate_id": ids["Ada"], "job_id": ids["backend"], "composite_score": 100}},
        {"action": "propose_shortlist", "candidate_ids": [ids["Ada"], ids["Cy"]]})))
    approve(ctx, saver, llm_run)
    assert ctx.session.query(AgentShortlist).count() == 1
    ctx.session.expire_all()
    assert _score_rows(ctx.session) == before


# --- LLM planner ---------------------------------------------------------------------------
def test_llm_planner_runs_tools_and_proposes(env):
    ctx, ids, saver = env
    fake = ScriptedLLM({"action": "call_tool", "tool": "search_candidates", "args": {"query": "React"}},
                       {"action": "propose_shortlist", "candidate_ids": [ids["Bo"]], "note": "Strong React."})
    result = run(ctx, saver, "Shortlist a frontend person", planner=agent.LLMPlanner(fake), job_id=ids["backend"])
    assert result["status"] == "pending_approval"
    assert [e["candidate_id"] for e in result["proposal"]["entries"]] == [ids["Bo"]]
    assert result["proposal"]["note"] == "Strong React."
    assert "<tool_results>\n(none yet)\n</tool_results>" in fake.prompts[0]
    assert '"candidate_name": "Bo"' in fake.prompts[1]


def test_shortlist_names_only_search_hits_or_ids_the_request_names_on_the_runs_job(env):
    ctx, ids, saver = env
    bo = ids["Bo"]
    looked_up = ScriptedLLM({"action": "call_tool", "tool": "get_candidate_profile", "args": {"candidate_id": bo}},
                            {"action": "propose_shortlist", "candidate_ids": [bo]})
    assert run(ctx, saver, "Shortlist someone", planner=agent.LLMPlanner(looked_up),
               job_id=ids["backend"])["proposal"] is None
    named = ScriptedLLM({"action": "propose_shortlist", "candidate_ids": [bo]})
    result = run(ctx, saver, f"Shortlist candidate {bo}", planner=agent.LLMPlanner(named), job_id=ids["backend"])
    assert [e["candidate_id"] for e in result["proposal"]["entries"]] == [bo]
    other_job = ScriptedLLM({"action": "call_tool", "tool": "search_candidates", "args": {"query": "React"}},
                            {"action": "propose_shortlist", "candidate_ids": [bo]})
    result = run(ctx, saver, "Shortlist a React person", planner=agent.LLMPlanner(other_job), job_id=ids["other"])
    assert bo in [h["candidate_id"] for h in result["steps"][0]["result"]["hits"]]
    assert result["proposal"] is None  # a search hit, but Bo applied to the backend job


@pytest.mark.parametrize("request_text,expected", [
    ("Compare candidates 3, 5 and 7 for job 2", [3, 5, 7]),
    ("candidate #9 vs #10", [9, 10]),
    ("Score id 4 for job #2", [4]),
    ("Shortlist the top 3 with 5 years of Python", []),
    ("Someone with 3.5 years", []),
])
def test_router_reads_only_marked_ids(request_text, expected):
    assert agent.named_ids(request_text) == expected


def test_llm_failure_ends_the_run_with_a_generic_message(env):
    ctx, _, saver = env

    class Down:
        name = "down"

        def generate(self, prompt):
            raise RuntimeError("503 secret upstream detail")
    result = run(ctx, saver, "anything", planner=agent.LLMPlanner(Down()))
    assert result["status"] == "error" and "secret" not in result["message"]


# --- providers -----------------------------------------------------------------------------
def test_provider_is_off_unless_enabled(monkeypatch):
    monkeypatch.delenv("AGENT_LLM_ENABLED", raising=False)
    assert agent_llm.get_provider() is None
    monkeypatch.setenv("AGENT_LLM_ENABLED", "true")
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "none")
    assert agent_llm.get_provider() is None


def test_gemini_is_the_default_and_goes_through_llm_py(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_ENABLED", "true")
    monkeypatch.delenv("AGENT_LLM_PROVIDER", raising=False)
    assert agent_llm.get_provider() is None  # no key: rule-based router
    monkeypatch.setattr(config, "get_api_key", lambda: "k")
    calls = []
    monkeypatch.setattr(llm, "generate_text", lambda prompt, key: calls.append(key) or "{}")
    provider = agent_llm.get_provider()
    assert provider.name == "gemini" and provider.generate("p") == "{}" and calls == ["k"]


def test_optional_providers_need_their_key_and_sdk(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_ENABLED", "true")
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def missing(name):
        raise ImportError(name)
    monkeypatch.setattr(agent_llm.importlib, "import_module", missing)
    with pytest.raises(agent_llm.ProviderError, match="pip install openai"):
        agent_llm.get_provider()
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "anthropic")
    with pytest.raises(agent_llm.ProviderError, match="pip install anthropic"):
        agent_llm.get_provider()
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "mystery")
    with pytest.raises(agent_llm.ProviderError, match="must be one of"):
        agent_llm.get_provider()
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "ollama")
    assert agent_llm.get_provider().name == "ollama"  # local server, no key


def test_optional_provider_without_a_key_falls_back_to_rules(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_ENABLED", "true")
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(agent_llm.importlib, "import_module", lambda name: object())
    assert agent_llm.get_provider() is None
    assert agent.make_planner(None) is agent.rule_based_planner


# --- decisions and checkpoints --------------------------------------------------------------
def test_every_decision_is_recorded_and_the_runs_checkpoints_are_deleted(env):
    from models import AgentDecision

    ctx, ids, saver = env
    rejected = run(ctx, saver, "shortlist python engineers", job_id=ids["backend"])
    approved = run(ctx, saver, "shortlist kubernetes engineers", job_id=ids["backend"])
    approve(ctx, saver, rejected, decision="reject", reviewer="Rita", note="not yet")
    approve(ctx, saver, approved, reviewer="Sam")
    rows = {r.thread_id: r for r in ctx.session.query(AgentDecision)}
    assert (rows[rejected["thread_id"]].decision, rows[rejected["thread_id"]].outcome,
            rows[rejected["thread_id"]].note) == ("reject", "rejected", "not yet")
    assert (rows[approved["thread_id"]].reviewer, rows[approved["thread_id"]].outcome) == ("Sam", "approved")
    assert rows[approved["thread_id"]].job_title == "Backend"
    for result in (rejected, approved):
        assert saver.get_tuple({"configurable": {"thread_id": result["thread_id"]}}) is None


def test_runs_that_never_pause_keep_no_checkpoints(env):
    ctx, _, saver = env
    result = run(ctx, saver, "Who has run Kubernetes clusters?")
    assert saver.get_tuple({"configurable": {"thread_id": result["thread_id"]}}) is None
