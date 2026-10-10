"""The read-only MCP server: the five tools, their annotations, errors, and rollback. No network server
is started; tools are listed and called in process."""
import asyncio
import json

import pytest
from sqlalchemy.orm import Session, sessionmaker

from database import create_database_engine
from tests.test_agent_tools import STORED_COMPOSITE, make_pool, no_model  # noqa: F401  (fixture)
from tests.test_retrieval import KeywordProvider

# mcp is optional (requirements-mcp.txt); without it these tests are skipped.
ToolError = pytest.importorskip("mcp.server.mcpserver.exceptions").ToolError
import mcp_server  # noqa: E402  (after the skip: it imports mcp)


@pytest.fixture
def served(tmp_path, no_model):  # noqa: F811
    engine = create_database_engine(f"sqlite:///{(tmp_path / 'mcp.db').as_posix()}")
    provider = KeywordProvider()
    with Session(engine) as session:
        ids = make_pool(session, provider)
    opened = []

    def sessions():
        session = sessionmaker(bind=engine)()
        opened.append(session)
        return session
    yield mcp_server.build_server(mcp_server.ReadOnlyTools(sessions, lambda: provider)), ids, opened
    engine.dispose()


def call(server, name, arguments):
    result = asyncio.run(server.call_tool(name, arguments))
    assert not result.is_error
    return json.loads(result.content[0].text)


def test_exposes_exactly_the_five_tools_all_read_only(served):
    server, _, _ = served
    tools = asyncio.run(server.list_tools())
    assert sorted(t.name for t in tools) == ["compare_candidates", "get_candidate_profile", "score_candidate",
                                             "search_candidates", "skill_gap_report"]
    for tool in tools:
        hints = tool.annotations
        assert (hints.read_only_hint, hints.destructive_hint) == (True, False)


def test_tools_return_the_same_results_as_the_agent_tools(served):
    server, ids, opened = served
    hits = call(server, "search_candidates", {"query": "Kubernetes", "job_id": ids["backend"]})["hits"]
    assert hits[0]["candidate_name"] == "Cy" and {"char_start", "char_end", "text"} <= set(hits[0])
    score = call(server, "score_candidate", {"candidate_id": ids["Ada"], "job_id": ids["backend"]})
    assert (score["source"], score["composite_score"]) == ("stored", STORED_COMPOSITE)
    rows = call(server, "compare_candidates", {"candidate_ids": [ids["Bo"], ids["Cy"]], "job_id": ids["backend"]})
    assert len(rows["rows"]) == 2
    assert call(server, "get_candidate_profile", {"candidate_id": ids["Bo"]})["name"] == "Bo"
    assert "missing_skills" in call(server, "skill_gap_report", {"candidate_id": ids["Bo"], "job_id": ids["backend"]})
    assert len(opened) == 5  # one session per call...
    assert all(not s.in_transaction() for s in opened)  # ...rolled back and closed


def test_errors_are_short_and_name_no_internals(served):
    server, ids, _ = served
    with pytest.raises(ToolError, match="candidate 999 not found"):
        asyncio.run(server.call_tool("score_candidate", {"candidate_id": 999, "job_id": ids["backend"]}))
    with pytest.raises(ToolError, match="greater than 0"):
        asyncio.run(server.call_tool("get_candidate_profile", {"candidate_id": 0}))
    with pytest.raises(ToolError):  # no approval or write tool exists
        asyncio.run(server.call_tool("approve_shortlist", {"thread_id": "x"}))


def test_refuses_to_start_unless_agent_llm_is_enabled(monkeypatch):
    started = []
    monkeypatch.setattr(mcp_server.MCPServer, "run", lambda self, transport: started.append(transport))
    monkeypatch.setenv("AGENT_LLM_ENABLED", "false")
    with pytest.raises(SystemExit, match="AGENT_LLM_ENABLED=true"):
        mcp_server.main()
    assert started == []
    monkeypatch.setenv("AGENT_LLM_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    mcp_server.main()
    assert started == ["stdio"]
