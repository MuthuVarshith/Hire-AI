# Final phase notes

Hire AI went from a Flask resume screener to a FastAPI recruiting assistant. It has login, retrieval-augmented question answering with streaming answers, a LangGraph agent whose shortlists a person must approve, a new dashboard, Docker and CI, and evaluation tooling.

Six agents built it in parallel from contracts committed first (`docs/contracts.md`, `app/auth.py`, `app/db.py`). The lead merged them into `upgrade/final` in the order B, A, D, C, E, F.

## What was built

| Area | Result |
|---|---|
| **API** (A) | FastAPI with one router per area. Every error is JSON: validation errors return 400 and keep Flask's messages, 404 and 405 are JSON, and 500s are generic with details logged. Body limits return 413. No CORS. Flask is removed |
| **Auth** (B) | Users with argon2id hashes. Sessions are random 256-bit tokens stored as SHA-256 hashes, sent as an HttpOnly `SameSite=Strict` cookie or as a Bearer token. Roles are admin and recruiter. `python -m app.cli create-admin`. Approvals record the signed-in user (migration 0006) |
| **Agent hardening** (B) | A stuck decision claim can be recovered. Checkpoints are pruned when a run raises. Step errors are fixed strings, never model text. Invisible-character stripping is wider |
| **Streaming chat** (D) | `POST /api/ask/stream`, using the token, citation, done and error events. It reuses `ask.py`'s steps, which were refactored for this. Gemini tokens stream as a provisional draft. Citations are validated at the end, and there is exactly one terminal event |
| **Dashboard** (C) | Login; streaming chat with clickable citations; the agent view with approve and reject; candidate comparison; jobs, candidates, analytics and templates. All text is inserted XSS-safe (`textContent`, no `innerHTML`) |
| **Deployment** (E) | A Dockerfile (non-root, model baked in so it runs with `HF_HUB_OFFLINE=1`) and Compose with PostgreSQL and pgvector. GitHub Actions run ruff, mypy, tests on SQLite and pgvector, and an image build. A Cloud Run plus Neon guide |
| **Evaluation** (F) | The judge provider and model are configurable, defaulting to an OpenRouter free model so Gemini doesn't grade itself. A combined mode makes one request per answer. The live runner was ported to FastAPI. `docs/how-to-run-eval.md` |

## Quick checks run by the lead

These are not full test suites; you said you'd run those.

**End to end through the merged app** (TestClient, throwaway SQLite, no LLM configured):
1. create the admin;
2. log in;
3. create a job;
4. upload two resumes;
5. screen one (score 70.79);
6. list by score, where the unscored candidate is kept and listed last;
7. `/api/ask` (passages only);
8. `/api/ask/stream` (8 citation events, then done);
9. an agent run, then approve;
10. an agent run, then reject;
11. a 405 that comes back as JSON;
12. logout, after which `/api/auth/me` returns 401.

All passed.

**Score-equality test:** 5 passed, including the 120 cases.

**Not run, and why:**
- `docker compose up`: the Docker Desktop engine isn't starting on this machine. `docker compose config` passes.
- Full suites, ruff and mypy across the repo: you said you'd run them.

**Live calls during the check:** 2 Gemini requests (1 success, 1 503), with synthetic sample data only. `config.get_api_key()` falls back to reading `.env` when `GOOGLE_API_KEY` is empty.

## Design choices and trade-offs

- **Contracts first, then parallel agents.** Six agents could build at once without editing each other's files. The cost was a few gaps that had to be reconciled at merge (`docs/contracts.md` section 8).
- **Server-side sessions over JWTs.** Logout really revokes a session, and there's no signing key to manage. The cost is a database lookup per request.
- **Cookie plus `SameSite=Strict` instead of a CSRF token.** It's simple for a same-origin dashboard. It assumes modern browsers, and it needs `FORWARDED_ALLOW_IPS` behind Cloud Run's proxy so the `Secure` flag is set.
- **SSE over `fetch`, not `EventSource`.** It allows POST with a JSON body. The client parses the frames itself.
- **The streamed draft is provisional, and only `done` is authoritative.** Citation validation needs the whole answer, so a draft can turn into "Not found in resumes." at the end.
- **The judge is a different model family** (OpenRouter free tier). This avoids self-grading. Free models change, and their limits are low.

## Known limitations

- **Login:** no rate limiting.
- **Agent:** a decision claim stuck in `record_retrying` can't be recovered automatically.
- **Streaming:** no keepalive ping.
- **Tests:** `tests/test_agent_api.py` and `tests/test_agent_api_edges.py` still target the old approve body and module.
- **Untested here:** migration 0006 on PostgreSQL, and the Docker image build.
- **Cloud Run scale-to-zero:** uploads and paused agent checkpoints don't survive it. Use object storage, or Postgres for checkpoints, in a real deployment.
- **Answer quality: not yet measured.** The golden set, held-out set, judge and cutoff recalibration are ready (`docs/how-to-run-eval.md`). The not-found cutoff is still the provisional 0.25.
- **Keyword stuffing** still raises the deterministic skill score. This is documented in `docs/security-injection.md`.

## Interview questions

1. **Why are a person's approval and the deterministic score kept outside the LLM's reach, and how is that enforced?** The tools are read-only and allow-listed. The graph pauses at a LangGraph `interrupt`, and only the approve endpoint resumes it. Shortlist IDs must come from tool results. Displayed scores come from `scorer.py`, and a test checks that stored scores are byte-identical before and after an agent run.
2. **How does the app stop two people approving and rejecting the same run at once?** A unique `agent_decisions` row is claimed before the graph resumes. Its failure states (`record_failed`, release markers) make retries safe.
3. **Why random tokens stored as hashes instead of JWTs?** Revocation, no key rotation, and a database leak doesn't expose usable tokens. The cost is one indexed lookup per request.
4. **How does streaming stay honest when citations can only be checked at the end?** Tokens are a provisional draft. Only the terminal `done` event carries the validated answer, and `error` marks the draft incomplete. There is exactly one terminal event.
5. **How do you defend against prompt injection in resumes?** Text goes in a delimited data block, with delimiter tags stripped after NFKC normalisation and removal of invisible characters. A "data, not instructions" rule, strict JSON parsing, citation checks, allow-listed tools, a call cap, and output vetting follow. Known limits: false claims that cite a real passage, and keyword stuffing.
6. **Why did you ship vector-only retrieval when hybrid and the reranker scored higher?** The gains were within bootstrap noise on 30 questions, under a decision rule frozen before the measurement.
7. **How do you evaluate answer quality on a free tier with 20 requests a day?** Answers are reused, judging is batched and resumable with request counting, there is a combined one-request judge mode, and a different-family judge model is used. The cutoff is calibrated on a held-out set, so the benchmark stays a test set.
8. **What would you change before real users and real resumes?** Add login rate limiting and auditing, move uploads and checkpoints to durable storage, run on PostgreSQL only, use a DPA-covered LLM provider (or none), add PII redaction in traces, and fix the open items above.
