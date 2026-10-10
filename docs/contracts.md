# Contracts for the final phase

Six agents build in parallel against this file, `app/auth.py` and `app/db.py`, exactly as committed. If a contract is missing something, an agent notes it in its report rather than editing another agent's files. The lead resolves gaps at merge time and records them at the end of this file.

## 0. Ownership and merge order

| Agent | Branch | Owns |
|---|---|---|
| **B: auth and agent hardening** | `agent-b/auth` | `app/auth.py` (implementation, same names and signatures), `app/routers/auth.py`, `app/cli.py`, `migrations/versions/0006_*.py`, the `User`/`Session` models (append to `models.py`, nothing else in it), `agent.py`, `text_guard.py` |
| **A: FastAPI migration** | `agent-a/fastapi` | `app/main.py`, `app/routers/*` except `auth.py` and `ask_stream.py`, `app/schemas/*`, `agent_api.py`, `legacy_flask_app.py` (port, then delete), `start.py`; porting the existing tests' Flask test client to FastAPI's `TestClient` (mechanical only, no new tests) |
| **D: streaming chat** | `agent-d/streaming` | `app/routers/ask_stream.py`, `app/ask_stream.py`, `ask.py` (refactor into reusable steps; `answer_question` keeps its signature and behaviour), `llm.py` (add a streaming function only) |
| **C: dashboard** | `agent-c/dashboard` | `templates/**`, `static/**`, deleting `frontend.html` |
| **E: deployment and CI** | `agent-e/deploy` | `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.github/workflows/**`, `deploy/**`, `docs/deploy-cloud-run.md`, `requirements*.txt`, `tests/conftest.py` (environment only) |
| **F: evaluation and docs** | `agent-f/eval` | `eval/**`, `docs/how-to-run-eval.md`, `docs/security-injection.md`, `tests/test_optional_eval_deps.py` |

**Merge order** (the lead): B, A, D, C, E, F. The README and `docs/final-notes.md` belong to the lead.

**Starting state, already done in Phases 3 and 4:**
- The stranded-run fix (`record_failed` and retry).
- `text_guard.visible()` in `_defang`.
- `HF_HUB_OFFLINE=1` in `tests/conftest.py`.
- `MAX_SERVER_ERROR_RETRIES`.

Verify these and build on them; don't redo them.

## 1. Application layout

- **The app.** `app/main.py` defines `app = FastAPI(...)`. Run it with `uvicorn app.main:app --host 127.0.0.1 --port 8000`. It includes every router, mounts `/static` from `static/`, and serves the two dashboard pages below.
- **Database.** `app/db.py` (committed, final) provides `engine`, `SessionLocal` and the dependency `get_session()`. The engine applies migrations when it is created.
- **Shared modules stay where they are and keep their behaviour:** `models.py`, `scorer.py`, `screening.py`, `ask.py`, `agent.py`, `agent_tools.py`, `retrieval.py`, `indexing.py` and the rest.
- **Flask.** It is gone at the end: `legacy_flask_app.py` (the old `app.py`, renamed so it doesn't clash with the `app/` package) is deleted once every route is ported, and `flask` and `flask-cors` leave the requirements.

**Dashboard pages**, served by `app/main.py` with no authentication on the page itself:

| Path | File |
|---|---|
| `GET /` | `templates/index.html` |
| `GET /login` | `templates/login.html` |
| `/static/*` | `static/` (JS, CSS) |

The pages are plain HTML and JS, with no server-side templating. On any API 401, the JS redirects to `/login`.

## 2. Route map

Paths, methods, status codes and response bodies stay as they were in Flask unless a cell says otherwise. **Auth:** R = `require_role("recruiter")` (admins pass too), A = `require_role("admin")`, P = public.

| Method | Path | Router file | Auth | Notes |
|---|---|---|---|---|
| POST | `/api/jobs` | `jobs.py` | R | JSON `{title, description_text, ...}` → 201 Job |
| GET | `/api/jobs` | `jobs.py` | R | → 200 `[Job]` |
| GET | `/api/jobs/{job_id}` | `jobs.py` | R | → 200 Job, 404 |
| PUT | `/api/jobs/{job_id}` | `jobs.py` | R | → 200 Job, 404 |
| DELETE | `/api/jobs/{job_id}` | `jobs.py` | R | → 200 `{"message": "Job deleted"}`, 404 |
| POST | `/api/candidates?job_id=` | `candidates.py` | R | multipart field `resume` → 201 Candidate, 400, 404, 413 |
| GET | `/api/candidates` | `candidates.py` | R | query `job_id`, `status`, `sort_by` → 200 `[Candidate with screening]`. **Fix:** with `sort_by=score`, unscored candidates are listed after scored ones, not dropped |
| GET | `/api/candidates/{candidate_id}` | `candidates.py` | R | → 200 Candidate with screening, 404 |
| PUT | `/api/candidates/{candidate_id}` | `candidates.py` | R | `{status?, notes?}` → 200, 400 (bad status), 404 |
| GET | `/api/candidates/{candidate_id}/resume` | `candidates.py` | R | file download, 404 |
| DELETE | `/api/candidates/{candidate_id}` | `candidates.py` | R | → 200 `{"message": "Candidate deleted"}`, 404 |
| POST | `/api/screen/{candidate_id}/{job_id}` | `scoring.py` | R | optional JSON options → 201 Screening, 404 |
| GET | `/api/screening/{screening_id}` | `scoring.py` | R | → 200 Screening, 404 |
| GET | `/api/candidates/{candidate_id}/jobs/{job_id}/interview-questions` | `scoring.py` | R | query `use_llm` → 200 list, 404 |
| POST | `/api/scoring-templates` | `templates.py` | R | → 201, 400, 409 (duplicate name) |
| GET | `/api/scoring-templates` | `templates.py` | R | → 200 `[Template]` |
| GET | `/api/scoring-templates/{template_id}` | `templates.py` | R | → 200, 404 |
| PUT | `/api/scoring-templates/{template_id}` | `templates.py` | R | → 200, 400, 404, 409 |
| DELETE | `/api/scoring-templates/{template_id}` | `templates.py` | R | → 200, 400 (the default template), 404 |
| GET | `/api/analytics/dashboard` | `analytics.py` | R | query `job_id` → 200 metrics object (unchanged) |
| GET | `/api/analytics/jobs/{job_id}` | `analytics.py` | R | → 200, 404 |
| GET | `/api/analytics/top-candidates` | `analytics.py` | R | query `job_id`, `limit` → 200 list |
| POST | `/api/ask` | `ask.py` | R | non-streaming, unchanged; calls `ask.answer_question` |
| POST | `/api/ask/stream` | `ask_stream.py` (D) | R | SSE, section 4 |
| POST | `/api/agent/run` | `agent.py` | R | unchanged body and response |
| POST | `/api/agent/approve/{thread_id}` | `agent.py` | R | **Changed:** body is `{decision, note?}`. The reviewer is the signed-in user; a `reviewer` field in the body is ignored |
| POST | `/api/auth/login` | `auth.py` (B) | P | section 3 |
| POST | `/api/auth/logout` | `auth.py` (B) | R | section 3 |
| GET | `/api/auth/me` | `auth.py` (B) | R | section 3 |
| GET, POST | `/api/auth/users` | `auth.py` (B) | A | list or create users |
| GET | `/api/health` | `health.py` | P | `{"status": "OK", ...}` |
| GET | `/api/info` | `health.py` | P | endpoint list, updated |

**Errors (A, in `app/main.py`).** Every error is JSON `{"error": "<message>"}`. Clients get generic messages for 500s, and the full details go to the server log.

| Status | When |
|---|---|
| 400 | validation errors; replaces FastAPI's default 422 |
| 401 / 403 | from auth |
| 404 | unknown resource or unknown route (JSON, not HTML) |
| 405 | `{"error": "Method not allowed"}` (JSON, not HTML) |
| 409, 410 | as today |
| 413 | body too large |
| 415 | JSON required |
| 500 | `{"error": "Internal server error"}` |

Explicit messages the Flask routes returned stay the same, for example `{"error": "title is required"}`.

**No CORS on `/api/*`.** The dashboard is same-origin.

## 3. Authentication

**`app/auth.py` (committed contract).**
- Route signatures use the aliases `Recruiter` and `Admin` (`Annotated[User, Depends(require_role(...))]`), or `Annotated[User, Depends(require_user)]`. Ruff's B008 rule forbids `Depends()` as a default value.
- `User(id: int, name: str, role: "admin" | "recruiter")`
- `require_user()` → User, or **401** `{"error": "Not authenticated"}`
- `require_role(*roles)` → User, or **403** `{"error": "Forbidden"}`. Admin always passes.
- `SESSION_COOKIE = "hireai_session"`

**Credentials.** Both are accepted:
- the session cookie: HttpOnly, `SameSite=Strict`, `Secure` when the request came over HTTPS;
- an `Authorization: Bearer <token>` header, for API clients and scripts.

Cross-site requests can't carry the Strict cookie, and every write is JSON or multipart behind auth, so no CSRF token is needed.

**Endpoints (B):**

| Request | Response |
|---|---|
| `POST /api/auth/login` `{"username", "password"}` | 200 `{"user": {"id", "name", "role"}, "token": "...", "expires_at": "ISO-8601"}`, and sets the cookie. 401 `{"error": "Invalid username or password"}`, the same message for an unknown user or a wrong password |
| `POST /api/auth/logout` | 204; revokes the session or token and clears the cookie |
| `GET /api/auth/me` | 200 `{"id", "name", "role"}` |
| `GET /api/auth/users` (admin) | 200 `[{"id", "name", "role", "created_at"}]` |
| `POST /api/auth/users` (admin) `{"username", "password", "role"}` | 201 user; 409 if the username is taken |

**Rules:**
- **Passwords:** argon2id via `argon2-cffi`, at least 12 characters, never logged. There are no default users or passwords.
- **First admin:** `python -m app.cli create-admin --username <name>` prompts for the password (getpass, typed twice). It refuses if that username exists.
- **Tokens:** stored server-side as a hash (in a `sessions` table) or signed with `AUTH_SECRET`. B decides and documents it. Expiry is `AUTH_TOKEN_TTL_HOURS` (default 12).
- **Migration** `0006` (B): `users`, and `sessions` if used, plus `agent_decisions.reviewer_id` (nullable integer, FK to `users.id`, SET NULL).

**Agent approval wiring (A calls, B implements).** The approve route calls:

`agent.resume_run(ctx, thread_id, {"decision": body.decision, "note": body.note, "reviewer": user.name, "reviewer_id": user.id}, planner, checkpointer)`

B extends `agent.Decision` to accept `reviewer_id: int | None`.

## 4. Streaming chat (Server-Sent Events)

**Request.** `POST /api/ask/stream`, auth R, JSON `{"question": str, "job_id": int | null}`. Validation is the same as `POST /api/ask`. A validation failure is an ordinary JSON 400 or 404, sent **before** the stream starts.

**Response.** `200`, `Content-Type: text/event-stream`, `Cache-Control: no-cache`. Each event is:

```
event: <type>
data: <one-line JSON>

```

A comment line `: ping` may be sent every 15 s.

| Event | Payload | Meaning |
|---|---|---|
| `token` | `{"text": str}` | A piece of the draft answer as the LLM writes it. **Provisional:** shown as a draft, never as the final answer |
| `citation` | `{"number", "candidate_id", "candidate_name", "section", "text", "char_start", "char_end", "similarity"}` | A validated passage, the same fields as `/api/ask` citations. Sent only after validation, just before `done` |
| `done` | `{"question", "found", "answer", "generated", "summary_unavailable", "summary_unavailable_reason", "top_similarity", "citation_numbers": [int]}` | **Terminal and authoritative.** The client replaces any draft with `answer` |
| `error` | `{"error": str, "code": "llm_failed" \| "internal"}` | **Terminal.** The client marks the draft incomplete and must not present it as an answer |

**Order and rules:**
1. Exactly one terminal event, `done` or `error`, then the stream closes.
2. **Below the cutoff:** `done` with `found: false` and `answer: "Not found in resumes."`. No tokens.
3. **No LLM** (off, no key, `ASK_LLM_ENABLED` false), or the LLM fails before the first token: one `citation` per passage, then `done` with `summary_unavailable: true` and a reason (`llm_disabled` or `llm_error`), and `generated: false`.
4. **LLM streaming:**
   - `token` events, then validation against the passages the LLM was given (the same rules as `ask.py`), then the valid `citation` events, then `done`.
   - If validation fails, the result is `done` with `found: false` and `answer: "Not found in resumes."`. The client discards the draft.
   - If the LLM fails after tokens have started: `error`.
5. The streamed draft is plain answer text with `[n]` markers, not JSON. D documents the streaming prompt in `app/ask_stream.py`.

## 5. Frontend API contract

The dashboard (C) calls only these, with `credentials: "same-origin"`.

**Shapes**

| Shape | Fields |
|---|---|
| **Job** | `id, title, description, required_skills[], preferred_skills[], min_experience_years, required_education, created_at, candidates_count, status ("Open" \| "Filled")` |
| **Candidate** | `id, name, email, phone, resume_filename, skills[], experience_years, education[], work_history[], status, created_at, notes, job_id, job_title`; plus `screening` (a Screening or null) on list and detail |
| **Screening** | `id, candidate_id, job_id, composite_score, semantic_score, skill_match_score, experience_score, education_score, matched_skills[], missing_skills[], matched_preferred_skills[], reasoning, strengths[], skill_gaps[], created_at` |
| **Template** | `id, name, description, semantic_weight, skill_weight, experience_weight, education_weight, is_default, created_at` |
| **Ask result** (`POST /api/ask`) | `question, found, answer, citations[Citation], generated, summary_unavailable, summary_unavailable_reason, top_similarity` |
| **Agent run** (`POST /api/agent/run` and approve) | `thread_id, status ("running" \| "pending_approval" \| "answered" \| "stopped" \| "approved" \| "rejected" \| "job_deleted" \| "candidates_deleted" \| "error"), message, steps[], proposal ({job_id, entries[{candidate_id, candidate_name, composite_score, score_source, matched_skills[], missing_skills[], citations[]}], note, note_removed, dropped_ids[]} \| null), decision, shortlist` |

**Calls by view:**
- **Login:** `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`.
- **Jobs:** list, create, get, update and delete jobs.
- **Candidates:** upload, list (filters and `sort_by`), detail, update status or notes, download resume, delete. Screening: `POST /api/screen/{c}/{j}`.
- **Comparison:** the candidates' detail and screening for one job, plus `GET /api/analytics/top-candidates?job_id=`.
- **Analytics:** `GET /api/analytics/dashboard`, `GET /api/analytics/jobs/{id}`.
- **Chat:** `POST /api/ask/stream`, read with `fetch` and a stream reader, since `EventSource` can't POST.
- **Agent:** `POST /api/agent/run`, `POST /api/agent/approve/{thread_id}`.
- **Scoring templates:** the CRUD routes above.

**XSS.** All user and resume text is inserted with `textContent` or escaped, never `innerHTML`.

## 6. Dependencies (E edits the requirements files; others list needs in their reports)

- **Add to core:** `fastapi>=0.143.0` (it allows starlette ≥0.46, so it can share an environment with `mcp`), `uvicorn[standard]`, `python-multipart`, `argon2-cffi`, `pyjwt` (if B uses signed tokens), `httpx` (for `TestClient`).
- **Remove:** `flask`, `flask-cors`. Keep `werkzeug` only if A still imports it; A reports this.
- **Optional files:** `requirements-eval.txt` (ragas, langfuse) and `requirements-mcp.txt` stay optional, and the production image never installs them.

## 7. Environment variables (new)

| Variable | Default | Owner |
|---|---|---|
| `AUTH_SECRET` | none; required in production | B |
| `AUTH_TOKEN_TTL_HOURS` | `12` | B |
| `JUDGE_PROVIDER` | `openrouter` | F |
| `JUDGE_MODEL` | a free OpenRouter model | F |
| `OPENROUTER_API_KEY` | none | F |

Existing variables are unchanged.

## 8. Gaps found during the build (lead fills in at merge)

_None yet._
