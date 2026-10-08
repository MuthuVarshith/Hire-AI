# Phase 0 notes: safety net before the upgrade

Phase 0 changes almost no behavior. Its job is to make later phases safe: pin down what the system does today, prove a scoring refactor changed nothing, and remove what was dead or deprecated.

## What was built

| Area | Change |
|---|---|
| Contract tests | 46 tests covering all 25 Flask routes: response bodies, validation errors, status codes and eight known defects. A Flask hook confirmed every route is exercised. |
| Parser tests | 25 tests: a snapshot of what the regex parsers extract from 12 sample resumes and 2 job descriptions, PDF and DOCX reading, unreadable files, and the Gemini path with a mocked model. |
| Score regression | 120 cases (2 job descriptions × 12 resumes × 5 scoring templates) captured from the original code and recomputed on every test run. |
| Scoring weights | `score_candidate` takes `weights` as an argument instead of reading a global dict that the API overwrote per request. |
| Deterministic parsing | Skill lists keep document order instead of the per-process order of `set()`. |
| Gemini SDK | `google-generativeai` (deprecated) replaced with `google-genai`; all five call sites go through `llm.py`; model name is the `GEMINI_MODEL` setting, default `gemini-3.8-flash`. |
| Config | `.env` loaded for both the web app and the CLI; the template placeholder key is no longer treated as a real key. |
| Cleanup | Removed Vercel leftovers (`api/`, `vercel.json`, `requirements-vercel.txt`), four unused dependencies, and unused settings in `.env.example`. |
| Tooling | `pyproject.toml` with ruff and strict mypy; `requirements-dev.txt`. |
| Docs | README: synthetic-data-only rule for Gemini and tracing services, test layout, new settings. |

**Results:** 126 tests pass (the original 33 plus 93 new). ruff and mypy are clean. Coverage of application code, measured with test files excluded, rose from 25% to 81%.

## Commits

Each commit is one concern and was verified on its own in a fresh checkout. The table shows the gates each passed:

| Commit | Change | Gates passed in isolation |
|---|---|---|
| `54642cf` | Replace deprecated `google-generativeai` with `google-genai` | 50 tests (linters not yet configured) |
| `d93686a` | Add ruff and mypy; remove dead deployment files and unused dependencies | ruff, mypy, 50 tests |
| `2316c52` | Make extracted skill lists deterministic; pin parser output | ruff, mypy, 75 tests |
| `8534370` | Pass scoring weights explicitly instead of mutating global `WEIGHTS` | ruff, mypy, 80 tests incl. the 120-case regression |
| `f1c3366` | Add contract tests for all 25 API routes | ruff, mypy, 125 fast tests |
| (this commit) | README updates and these notes | — |

## Design decisions and why

### 1. Characterization tests before any refactor
The brief moves the API from Flask to FastAPI in Phase 5. Before this phase, no route had a single test, so a migration could change behavior silently. A *characterization test* asserts what the code currently does, not what it should do. That makes it the exact contract a rewrite must keep. Where current behavior is wrong, the test is named `test_known_issue_*` and asserts the wrong behavior, so a fix has to update the test on purpose rather than slip through.

### 2. Proving the scoring refactor is behavior-preserving
"I changed the weights mechanism and the scores look the same" isn't evidence. The proof was set up so it couldn't be biased by the new code:
1. Captured 120 baseline results from **unmodified** commit `e2563a7`, mirroring exactly what the API did (overwrite `WEIGHTS`, score, restore).
2. Refactored.
3. Recomputed all 120 through the new code path, comparing every field.

Result: **0 of 120 cases have any numeric difference**, across two independent runs with different hash seeds. The baseline is committed, and the comparison runs on every test run as a permanent regression test, exact when the environment matches and ±0.01 otherwise.

The suite was also run in a fresh virtual environment installed only from `requirements-dev.txt`. pip picked newer libraries there than the ones that captured the fixture:

| Library | Fixture captured with | Fresh environment |
|---|---|---|
| torch | 2.7.1 | 2.14.1 |
| sentence-transformers | 5.6.1 | 6.1.0 |
| numpy | 2.2.6 | 2.5.3 |

All **120 of 120 cases were still bit-identical** (largest difference 0.0), and all 126 tests, ruff and mypy passed. The tolerance exists for safety, but no environment tried so far has needed it.

### 3. Why the global-weights mechanism had to go
The API applied a role's scoring template by overwriting a module-level dict, scoring, then restoring it. That has two defects:
- **A race:** two concurrent requests can interleave, so a candidate gets scored with another job's weights. With Flask's threaded server it's possible today; with async FastAPI it would be routine.
- **No restore on error:** if scoring raised an exception, the restore never ran, and every later candidate was scored with the wrong weights until restart.

Passing weights as an argument removes shared mutable state entirely; there's nothing left to lock. A test runs 400 concurrent scorings with alternating weights and checks each result.

### 4. The determinism fix
The baseline comparison surfaced a pre-existing bug: skill lists were built with `list(set(...))`, and Python randomizes string hashing per process. So a job's required-skill order changed every time the server restarted, which changed which three skills the dashboard showed. Scores were unaffected, since they count matches rather than order. `dict.fromkeys` keeps first-seen order and still de-duplicates. A test parses all samples in two processes with different hash seeds and requires identical output. A comparison against the original parsers from `e2563a7` found 0 field differences once order is ignored.

### 5. One wrapper for the LLM
Five modules each built a Gemini client, and three duplicated the same code-fence-stripping JSON parsing. `llm.py` is now the only module that imports the SDK. That made the SDK swap one change instead of five, lets tests block network access in one place (any test that reaches the real LLM fails), and is the seam Phase 3's provider switch (Gemini, OpenAI, Claude, Ollama, none) plugs into.

### 6. A mypy ratchet instead of a big-bang typing pass
Strict mypy on all legacy code reports 39 errors. Most trace to one root cause: `models.py` uses SQLAlchemy's untyped 1.x style (`declarative_base`, bare `Column`), so every module that touches a model inherits errors. Phase 1 rewrites the data layer with typed `Mapped[...]` models anyway. So the 13 legacy modules start on an explicit exemption list in `pyproject.toml`, new code is strict from day one, and modules leave the list as they're typed. The list can only shrink.

## Trade-offs

| Choice | Benefit | Cost |
|---|---|---|
| Characterization tests pin bugs | Any behavior change is deliberate and visible | Eight tests assert wrong behavior and must be rewritten when fixed |
| Committed score baseline | Permanent, automatic proof | Tied to an embedding-library version; other environments get a ±0.01 tolerance instead of exact equality |
| Snapshot of parser output | Catches any extraction change | A snapshot can rubber-stamp a bug; an intentional change needs `make_parser_snapshot.py` and a reviewed diff |
| Skill lists compared as sets against the baseline | Matches what the original code guaranteed | Can't detect an ordering regression against the original; the separate determinism test covers order going forward |
| Regression test loads the real model | Exercises the semantic path the other tests skip | About a minute per run; marked `slow` so `-m "not slow"` skips it |
| mypy exemption list | Strict typing now, without a risky rewrite of untouched code | 39 known type errors remain in legacy modules until they're typed |
| Default `gemini-3.8-flash` | Current stable Flash model per Google's models page | Couldn't confirm free-tier availability without a key; Google now shows quotas per project in AI Studio |

## Known issues found (pinned by tests, not yet fixed)

| # | Issue | Severity | Proposed fix |
|---|---|---|---|
| 1 | **Same-second uploads with the same file name overwrite each other.** Stored names are `<timestamp to the second>_<name>`, so one candidate can be served another's resume, and a rejected duplicate can delete the original's file. | **High: data loss and wrong-person PII** | Phase 1, first commit: unique names (UUID). |
| 2 | Deleting a job deletes its candidates but leaves their resume files on disk. | Medium: orphaned PII | Phase 1, with the storage change |
| 3 | Duplicate template name returns 500 with the SQL statement and parameters in the response. | Medium: information disclosure | Phase 5 consistent error responses |
| 4 | Non-JSON body to `POST /api/jobs` returns 500 instead of 415. | Low | Phase 5 request validation |
| 5 | Upload over 10 MB returns 500 instead of 413. | Low | Phase 5 |
| 6 | Non-string `status` in `PUT /api/candidates/<id>` returns 500 instead of 400. | Low | Phase 5 request validation |
| 7 | `sort_by=score` silently drops candidates who were never scored. | Low: misleading list | Phase 5 (outer join, unscored last) |
| 8 | A failed Gemini explanation stores an empty rationale instead of the template text. | Low | Phase 3, when LLM calls move behind the provider interface |
| 9 | 405 errors return an HTML page; every other error is JSON. | Low | Phase 5 |
| 10 | Every 500 response includes the raw exception message. | Medium: leaks internals | Phase 5 |

Also noted, untested: CSV/JSON export exists only in the CLI, not the web API; `main.py` and `start.py` have no tests (0% coverage).

## Interview questions you should be able to answer

**1. "How did you prove your refactor didn't change any scores?"**
A strong answer covers:
- The baseline came from the **old** code before any change, so the new code couldn't influence it.
- It covered the whole input space that mattered: 2 job descriptions × 12 resumes × 5 weight templates.
- Every output field was compared: four signal scores, the composite, and matched/missing skills.
- The proof turned up nondeterminism: skill *order* differed between runs of the *same* code. That was traced to hash randomization, fixed, and checked against the original parsers (0 field differences).
- The proof is a committed regression test, exact on the same environment and with a stated tolerance elsewhere.

**2. "What was wrong with mutating a global weights dict per request?"**
- Shared mutable state under concurrency: interleaved requests read each other's weights, and an exception skipped the restore, corrupting every later score.
- The fix is to make the dependency explicit (pass weights in). That removes the shared state rather than guarding it with a lock, which would have serialized all scoring.
- Mention the 400-call threaded test, and why async FastAPI would make the race routine rather than rare.

**3. "Why write tests that assert buggy behavior?"**
- Characterization tests exist to detect *any* behavior change during a rewrite (here, Flask to FastAPI).
- If a known bug were simply excluded, a migration could change it silently, for better or worse, with no review.
- Pinning it makes every fix an explicit, reviewed test change, and the notes track which phase fixes which issue.
- Trade-off to acknowledge: the tests must be maintained, and a snapshot can lock in a bug nobody noticed; that's why the found issues are listed explicitly instead of left implicit.
