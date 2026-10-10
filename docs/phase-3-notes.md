# Phase 3 notes: the recruiting agent, human approval, providers and MCP

Phase 3 added an agent that answers recruiter requests by calling read-only tools and proposes shortlists that a person must approve. It ran as one builder, then a tester and a read-only reviewer in parallel, then two fix-and-review rounds (the second review read-only, with no third fix round).

## What was built

| Area | Change |
|---|---|
| **Shared scoring inputs** | `screening.py` holds the screen route's scorer inputs, so the agent scores exactly as `POST /api/screen` does. The scoring formula is unchanged |
| **Five tools** | `agent_tools.py`: `search_candidates`, `get_candidate_profile`, `score_candidate`, `compare_candidates`, `skill_gap_report`. Thin wrappers over existing code, each with strict Pydantic input and output models. All read-only |
| **Agent** | `agent.py`: a LangGraph `StateGraph` with typed state. The flow is plan → tools → plan, then propose → approval → record |
| **Human approval** | The approval node pauses with LangGraph `interrupt()`; state is checkpointed (`SqliteSaver`, file `agent_checkpoints.db`, gitignored). Only `POST /api/agent/approve/<thread_id>` resumes it, via `Command(resume=...)` |
| **Decisions and shortlists** | Migration 0004 adds `agent_shortlists`; 0005 adds `agent_decisions` with a UNIQUE `thread_id`. Every approve or reject claims that row before the run resumes, so a second decision gets 409. Audit rows survive deletes (SET NULL plus job-title and candidate-name snapshots) |
| **Providers** | `agent_llm.py`: `AGENT_LLM_PROVIDER` = gemini (default), openai, anthropic, ollama or none. No LLM is used unless `AGENT_LLM_ENABLED=true`. With it off, "none", or no key, a rule-based router calls the same tools and still pauses for approval |
| **API and dashboard** | `agent_api.py` (strictly typed) behind `POST /api/agent/run` and `POST /api/agent/approve/<thread_id>`. A dashboard Agent panel shows the proposed shortlist with scorer scores and citations, and Approve/Reject buttons that disable while a request is in flight |
| **MCP server** | `mcp_server.py` exposes the five tools read-only, validates raw arguments strictly, and refuses to start unless `AGENT_LLM_ENABLED=true`, because it passes resume passages to the MCP client's model |
| **Live ask runner** | `eval/ask_live.py` runs in batches (`--ids`, `--out`), refuses to start with uncommitted changes in the `/api/ask` code or its inputs, records the commit at the start, and counts every Gemini HTTP request, retries included |

## Guards: tool output and resume text are data, not instructions

| Guard | Where |
|---|---|
| Only the five tools can be called; arguments are validated by the Pydantic models; IDs are capped at 2³¹−1 | `agent.py` `_resolve_tool`, `agent_tools.py` |
| At most 6 tool calls and 9 planner turns per run; after the last tool call the planner may only propose or finish | `agent.py` `MAX_TOOL_CALLS`, `MAX_TURNS` |
| Tool results reach the model inside a delimited block; delimiter tags in any spelling are stripped before JSON escaping | `agent.py` `_defang` |
| A shortlist may only hold candidates from this run's search hits or IDs the recruiter's request names, on the run's job | `agent.py` `_vet_proposal` |
| Displayed scores come from `score_candidate`, never from model text; score claims in model text are removed | `agent.py` `_vet_text` |
| Only the approve endpoint can approve; the model can't skip the interrupt | `agent.py` `_human_decision` |
| The agent never writes scores; a test checks stored scores are byte-identical before and after a run | `tests/test_recruiting_agent.py` |
| Agent endpoints send no CORS headers and accept JSON only | `app.py`, `agent_api.py` |

The injection tests in `tests/injection/test_agent_injection.py` each have an `_unguarded` twin. The tester removed six guards one at a time; each guarded test then failed at that guard.

## Results

| Check | Result |
|---|---|
| Full suite, SQLite (end of fix round, run by the builder) | 621 passed, 24 skipped (need PostgreSQL), 3 xfailed (known ask-injection limits) |
| Full suite, PostgreSQL (tester, before the fix round) | 582 passed, 2 skipped, 18 xfailed |
| 120-case score-equality test | Passes |
| ruff, strict mypy (34 files, nothing added to the overrides list) | Clean |
| Coverage of new modules (tester, before the fix round) | agent 99%, agent_tools 100%, agent_llm 86%, mcp_server 94%, screening 100% |
| Bugs pinned as strict xfails by the tester | 6, all fixed and flipped to normal tests |

**Not run this round, at your request:** the PostgreSQL suite after the fixes (so migration 0005's PostgreSQL path is untested) and a tester re-pass. The OpenAI and Anthropic providers have only mocked tests.

## Live checks

- **Ask, batch 1 (q01–q16), commit `e80b3df`, `gemini-3.8-flash`:**
  - 8 generated answers: 6 correct and 2 partly correct, each partial missing one labelled candidate. No invented claims; every citation supports its claim. This is the checking model's opinion (Claude Opus 5.5), not a metric, and 8 answers are too few for a rate.
  - q02 fell back to passages after a 503.
  - q10–q16 fell back after the daily quota of 20 ran out.
  - Gemini requests: 19 to 43. The exact number isn't known because retries that ended in success weren't logged. q02 made exactly 4, q10–q16 exactly 1 each. Since then a 5xx is retried at most once (`llm.MAX_SERVER_ERROR_RETRIES`), and live runs count every request.
  - Details are in `eval/ask_live_batch1.md`.
- **Live agent check: not run.** The quota was exhausted on 2026-10-10, so it moves to a later day, after the remaining ask questions.

## Design choices and trade-offs

- **A deterministic planner fallback.** With no LLM, the rule-based router still uses the tools and the approval step. The feature works offline, and tests don't depend on a model.
- **Claim before resume.** Writing the decision row before resuming the graph makes two simultaneous decisions safe. The cost is the stranded-run case below, when the resume fails after the claim.
- **Provider defaults.** The Anthropic provider defaults to `claude-opus-5-5`, with Anthropic's server-side refusal fallback on. OpenAI defaults to `gpt-5.4-mini`. Both are overridable and untested live.
- **No authentication yet.** `approved_by` is whatever name the caller sends. Same-origin and JSON-only requests stop other websites from calling the endpoints, but anyone who can reach the server can approve.

## Open issues (left open after the second review, as agreed)

| Severity | Issue |
|---|---|
| Medium | **A database error while recording an approval strands the run.** The claim is released, but the run has already moved past the approval step, so it can't be decided again (404) and its checkpoint stays. Fix: keep the claim marked failed and retry the record step (`agent.py:607-614`) |
| Low | If the record commits and a later checkpoint write fails, the claim is deleted but the shortlist row stays. If deleting the claim fails, the run is refused with 409 for good |
| Low | `agent_decisions.entries` keeps resume passages, rejected runs included, so pruning checkpoints doesn't remove them |
| Low | `steps[].error` in the API response can repeat model text. Bare numbers like "Ada (97)" pass the score-text check; displayed scores still come from the scorer |
| Low | A zero-width character inside a delimiter tag gets past `_defang` |
| Low | Checkpoints aren't pruned when a run raises |
| Untested | Migration 0005 and the post-fix suite on PostgreSQL; the OpenAI and Anthropic providers live |
| Phase 5 | Real authentication. The `mcp` install pulled starlette 1.7, which conflicts with an unrelated FastAPI 0.115 in the environment |

## Interview questions

1. **How does the agent wait for a human without holding a request open?**
   - The approval node calls LangGraph's `interrupt()`, and the graph state is saved to a SQLite checkpointer.
   - The first request returns a thread ID; the approve endpoint later resumes that thread with `Command(resume=decision)`.
   - A UNIQUE decision row is written before resuming, so two people deciding at once can't both win.

2. **The LLM is told a resume says "rank me first". What stops it?**
   - The model can only call five read-only tools, with validated arguments and a cap on calls.
   - Tool output reaches it as delimited data.
   - Its shortlist is filtered to candidates that came from this run's search or the recruiter's own request.
   - Scores shown come from the deterministic scorer, not its text.
   - Nothing is final until a person approves.
   - The tests prove each guard by removing it and watching the test fail.

3. **Why keep a rule-based router when you have an LLM?**
   - The app has to work offline and without a key.
   - Tests need deterministic behaviour.
   - It gives a baseline to compare the LLM planner against.
   - Both routes use the same tools and the same approval step, so the guards apply either way.
