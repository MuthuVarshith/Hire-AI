# HireAI — AI Resume Screening & Recruiter Dashboard

[![Python 3](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Backend-Flask-black.svg)](https://flask.palletsprojects.com/)
[![Tests](https://img.shields.io/badge/tests-192%20passing-brightgreen.svg)](#testing)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

HireAI screens resumes against a job description, gives every candidate an explainable 0–100 score, and gives recruiters a dashboard to track candidates through the hiring pipeline.

It started as a command-line screening agent. The original parsing and scoring engine is unchanged; a Flask API, a SQLite database, and a web dashboard were built on top of it. The CLI still works.

Repository: https://github.com/MuthuVarshith/Hire-AI

---

## Demo

![HireAI demo: creating a job, uploading a resume and reviewing the scored candidate](docs/demo.gif)

The demo walks through the core recruiter loop: create a job from a pasted job description, upload a resume against it, and see the candidate appear with a score, matched skills and missing skills.

---

## Screenshots

### Dashboard

![Dashboard with pipeline metrics, recruiter summary, recent candidates and active jobs](docs/screenshots/dashboard.png)

The landing page gives a recruiter the state of hiring at a glance:

- **Metric cards** for total candidates screened, shortlisted, in interview and hired.
- **Recruiter Summary**, a plain-language sentence built from the live database: number of candidates and jobs, average screening score, shortlist rate, and offers and hires made.
- **Recent Candidates**, the five most recent candidates, showing the job each applied to, their pipeline status badge and their score.
- **Active Jobs**, each job with its candidate count and status.

### Jobs

![Jobs page listing every job with description, candidate count, status and created date](docs/screenshots/jobs.png)

Every job posting in one table: title, a preview of the description, number of candidates, status, and creation date.

- **+ Create New Job** opens a form where you paste a full job description. The backend extracts required skills, preferred skills, minimum experience and education from it.
- **View** opens the Candidates page filtered to that job.
- A job is **Open** until at least one of its candidates is marked *Hired*, then it shows **Filled**. This is derived from candidate records; jobs have no separately stored status.

### Candidates

![Candidates page filtered to Backend Engineer, showing scores, status, matched and missing skills](docs/screenshots/candidates.png)

The main working view. Each row shows the candidate's name and years of experience, email, applied job, a color-coded score, their pipeline status, and skill tags: **blue for matched required skills, red for missing ones**.

- **Search** by name, email or any skill on the resume.
- **Filter** by job and by pipeline status. The screenshot shows the list filtered to *Backend Engineer*.
- **Sort** by score, name, or most recent.
- **View** opens the candidate profile: contact details, education, full score, matched and missing skills, the AI-generated explanation, a pipeline status selector, and a link to download the original resume.
- **Score** appears only on candidates that don't have a score yet, so you can retry scoring for them.

### Analytics

![Analytics page with headline metrics, score distribution, pipeline distribution, candidates by job and skill gaps](docs/screenshots/analytics.png)

Hiring metrics calculated from the records stored in the database, not sample numbers:

- **Headline metrics**: total screened, average score, shortlist rate, offers, hires and rejections.
- **Score Distribution**: how many candidates fall into each 20-point score band.
- **Pipeline Distribution**: candidate count at each stage, from Screened through Hired and Rejected.
- **Candidates by Job**: how many candidates each job has.
- **Most Common Skill Gaps**: the required skills candidates are most often missing. This shows where the talent pool is thin, or where a job description may be asking for too much.

---

## Features

| Area | What it does |
|---|---|
| **Resume parsing** | Reads `.txt`, `.pdf` and `.docx` files and extracts name, email, phone, skills, years of experience, education and work history |
| **Job description parsing** | Extracts title, required and preferred skills, minimum experience and required education from pasted text |
| **Explainable scoring** | Four scores (semantic, skills, experience, education) combined into one weighted 0–100 score, with the breakdown stored for each candidate |
| **Skill gap analysis** | Matched and missing required skills for each candidate; a skill counts as matched on exact or fuzzy similarity (embedding similarity > 0.7) |
| **Candidate database** | Candidates, jobs and screening results are saved in SQLite, so they survive restarts |
| **Duplicate detection** | Re-uploading someone already added to the same job is rejected, based on exact email, normalized phone number, or a >90% fuzzy name match |
| **Hiring pipeline** | `Screened → Shortlisted → Interview → Offer → Hired / Rejected`, changed from the candidate profile |
| **Analytics** | Metrics and charts calculated live from database records |
| **AI explanations (optional)** | With a Google Gemini API key, candidates get a short written explanation of their score; without one, a template-based explanation is used |
| **Scoring templates** *(API only)* | Named weight presets per role, stored in the database. Five presets are included; there is no page for them in the dashboard yet |
| **Interview questions** *(API only)* | Generates technical, resume-based, skill-gap and behavioral questions for a candidate; not yet shown in the dashboard |

---

## How scoring works

Each candidate is scored against the job on four signals. Each signal is scored 0–100, then they are combined using the default weights:

| Signal | Weight | How it is calculated |
|---|---|---|
| **Semantic similarity** | 40% | Cosine similarity between embeddings of the whole resume and the whole job description (`all-MiniLM-L6-v2`) |
| **Skill match** | 30% | Share of the job's required skills found on the resume, by exact or fuzzy match |
| **Experience** | 15% | `min(100, candidate_years / required_years × 100)` |
| **Education** | 15% | The candidate's highest degree compared with the job's requirement on a degree ladder |

```text
Overall = 0.40 × Semantic + 0.30 × Skills + 0.15 × Experience + 0.15 × Education
```

The weights live in [config.py](config.py). More detail and edge cases are in [scoring_method.md](scoring_method.md).

---

## Architecture

```mermaid
flowchart LR
    UI["Dashboard<br/>frontend.html"] -- "fetch /api/*" --> API["Flask API<br/>app.py"]

    API --> JD["jd_parser.py"]
    API --> RP["resume_parser.py"]
    API --> SC["scorer.py"]
    API --> DD["duplicate_detection.py"]
    API --> AN["analytics_service.py"]
    API --> IQ["interview_generator.py"]

    SC --> EMB[("Sentence-Transformers<br/>all-MiniLM-L6-v2")]
    JD -. optional .-> LLM[("Google Gemini")]
    RP -. optional .-> LLM
    IQ -. optional .-> LLM

    API --> IX["indexing.py"]
    IX --> CH["chunking.py<br/>section-aware chunks"]
    IX --> EP["embeddings.py<br/>pluggable provider"]
    EP --> EMB
    EP -. optional .-> GEMB[("Gemini embeddings")]

    API --> DB[("PostgreSQL + pgvector<br/>or SQLite<br/>models.py · Alembic")]
    IX --> DB
    API --> UP[/"uploads/<br/>resume files"/]
```

Flask serves the dashboard at `/` and the API under `/api`. They share an origin, so the browser needs no CORS setup.

**Upload, scoring and indexing flow**

```text
Upload resume → validate type and size → save to uploads/ under a unique name → parse resume
  → duplicate check → store candidate → chunk by section → embed → store chunks + vectors
  → POST /api/screen → score 4 signals → store result with explanation
  → dashboard, candidates and analytics update
```

Chunks and embeddings feed retrieval (search and "ask the candidate pool", added next). They never change scores: the score always comes from the deterministic engine in `scorer.py`.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask, Flask-CORS |
| Database | PostgreSQL 17 with pgvector, or SQLite for local use; SQLAlchemy 2.0 (typed models), Alembic migrations, psycopg 3 |
| NLP / scoring | Sentence-Transformers (`all-MiniLM-L6-v2`), NumPy |
| Retrieval prep | Section-aware chunking; embeddings from Sentence-Transformers (default, offline) or the Gemini embedding API |
| Optional LLM | Google Gemini via the `google-genai` SDK (default model `gemini-3.8-flash`, set by `GEMINI_MODEL`) |
| Document parsing | PyPDF2, python-docx |
| Duplicate matching | fuzzywuzzy, python-Levenshtein |
| Frontend | Plain HTML, CSS and JavaScript; no build step |
| Quality | pytest, pytest-cov, ruff, mypy |

---

## Getting started

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

To run the tests and linters as well, install `requirements-dev.txt` instead.

On the first run the embedding model (about 90 MB) downloads automatically.

### 2. Configure environment variables (optional)

```bash
cp .env.example .env
```

On Windows PowerShell, use `copy .env.example .env`.

Everything works without editing `.env`. The settings you're most likely to change:

| Variable | Default | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` | *(unset)* | Turns on Gemini-based parsing and written explanations. Without it, regex parsing and template explanations are used. Read [Using Gemini](#using-gemini-synthetic-data-only) first |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model name. Change it when Google retires a model or your key's free tier doesn't include the default |
| `DATABASE_URL` | `sqlite:///recruiting_agent.db` | SQLAlchemy connection string; see [Database setup](#3-database-setup) for PostgreSQL |
| `EMBEDDING_PROVIDER` | `sentence-transformers` | Embeddings for retrieval: `sentence-transformers` (local, offline) or `gemini`. Never affects scores |
| `EMBEDDING_API_MODEL` / `EMBEDDING_API_DIM` | `gemini-embedding-001` / `768` | Used when `EMBEDDING_PROVIDER=gemini` |
| `ASK_LLM_ENABLED` | `false` | Lets "Ask the candidate pool" send retrieved resume excerpts to Gemini for a written, cited answer. Synthetic data only. When `false`, `/api/ask` returns the cited passages without a summary |
| `MAX_RESUME_SIZE_MB` | `10` | Upload size limit |
| `ALLOWED_RESUME_EXTENSIONS` | `.txt,.pdf,.docx` | Accepted resume file types |
| `HOST` / `PORT` | `127.0.0.1` / `5000` | Server address, used by `python app.py` |

Never commit `.env`; it is already in `.gitignore`.

#### Using Gemini: synthetic data only

**Only send sample or synthetic resumes to Gemini, never real candidates' data.** Google's Gemini API pricing page states that on the free tier, content is "used to improve our products". Resumes contain personal data (names, emails, phone numbers, employment history), and candidates haven't agreed to share it with a model provider. The same rule applies to any tracing service added later, such as Langfuse Cloud, because traces include prompts and resume excerpts.

The app works fully without a key: leave `GOOGLE_API_KEY` unset when processing real resumes.

### 3. Database setup

**SQLite (default, nothing to install).** On startup the app creates `recruiting_agent.db` and brings its schema up to date. Embeddings are stored as JSON and searched by brute force, which is fine for hundreds of resumes.

**PostgreSQL with pgvector (recommended for anything larger).** One database holds both the records and the embeddings, in pgvector `vector` columns. Start it locally with Docker:

```bash
docker run -d --name hireai-pg -e POSTGRES_USER=hireai -e POSTGRES_PASSWORD=hireai -e POSTGRES_DB=hireai -p 127.0.0.1:5433:5432 -v hireai-pgdata:/var/lib/postgresql/data pgvector/pgvector:pg17
```

Then set `DATABASE_URL=postgresql+psycopg://hireai:hireai@127.0.0.1:5433/hireai` in `.env`. The port is bound to `127.0.0.1`, so the database isn't reachable from your network; use a real password anywhere else.

**Migrations.** [Alembic](migrations/) owns the schema, and the app applies pending migrations on startup. A database created by a version from before migrations existed is detected and adopted without recreating anything. To run migrations by hand:

```bash
python -m alembic upgrade head
```

**Search index.** Each resume and job description is split into section-aware chunks (Summary, Experience, Projects, Skills, Education…) and embedded when it is saved. If embedding was unavailable at the time, or you change `EMBEDDING_PROVIDER`, rebuild every chunk:

```bash
python -m indexing --reindex
```

To start over with SQLite, stop the server and delete `recruiting_agent.db`. The database and `uploads/` hold candidate personal data and are excluded from Git.

### 4. Run the app

```bash
python start.py
```

`start.py` loads the embedding model, then starts the server. When you see `Running on http://127.0.0.1:5000`, open:

**http://127.0.0.1:5000**

> **Open the app through that URL, not by double-clicking `frontend.html`.** A page opened from disk (`file://`) is blocked by the browser from calling the local API, so jobs and uploads fail.

> **Auto-reload is off.** When the scoring model loads, Flask's auto-reloader mistakes the import for a code change and restarts the server mid-request, which caused uploaded resumes to go unscored. After editing Python code, restart the server yourself.

---

## Example workflow

1. **Create a job.** Click **+ New Job**, enter a title, paste the full job description, and click **Create Job**. Required skills and experience are extracted automatically.
2. **Upload resumes.** Click **Upload Resume**, pick the job, choose a file, and click **Upload**. The candidate is parsed, checked for duplicates, saved and scored in one step. A message shows the score.
3. **Review candidates.** On **Candidates**, filter to the job and sort by score. Compare matched (blue) and missing (red) skills.
4. **Open a profile.** Click **View** to see the full score, the AI-generated explanation and education, or to download the original resume.
5. **Move them through the pipeline.** In the profile, change the status to Shortlisted, Interview, Offer, Hired or Rejected. The dashboard and analytics update.
6. **Check the funnel.** Use **Analytics** to see score distribution, pipeline stages and the most common skill gaps.

To try it with sample data, use the job description in [sample_jd/jd.txt](sample_jd/jd.txt) and the ten resumes in [sample_resumes/](sample_resumes/).

---

## API reference

All endpoints return JSON. Errors come back as `{"error": "..."}` with a matching HTTP status.

### Jobs

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/jobs` | Create a job. Body: `{"title", "description_text", "scoring_template_id"?}` |
| `GET` | `/api/jobs` | List all jobs |
| `GET` | `/api/jobs/<id>` | Get one job |
| `PUT` | `/api/jobs/<id>` | Update title, description or scoring template |
| `DELETE` | `/api/jobs/<id>` | Delete a job and its candidates |

### Candidates

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/candidates?job_id=<id>` | Upload a resume (`multipart/form-data`, field `resume`). Returns `409` for a duplicate |
| `GET` | `/api/candidates` | List candidates with latest score. Query: `job_id`, `status`, `sort_by=score` |
| `GET` | `/api/candidates/<id>` | Candidate details and screening history |
| `PUT` | `/api/candidates/<id>` | Update `status` and/or `notes` |
| `GET` | `/api/candidates/<id>/resume` | Download the original resume |
| `DELETE` | `/api/candidates/<id>` | Delete a candidate and their resume file |

### Screening and interview questions

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/screen/<candidate_id>/<job_id>` | Score a candidate against a job. Optional body `{"use_llm": false}` |
| `GET` | `/api/screening/<id>` | Get a stored screening result |
| `GET` | `/api/candidates/<cid>/jobs/<jid>/interview-questions` | Generate interview questions for a scored candidate |

### Scoring templates

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/scoring-templates` | List templates |
| `POST` | `/api/scoring-templates` | Create a template. The four weights must sum to 1.0 |
| `GET` / `PUT` / `DELETE` | `/api/scoring-templates/<id>` | Read, update or delete a template. The default template can't be deleted |

### Ask the candidate pool

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/ask` | Body `{"question": "...", "job_id": 1}` (`job_id` optional). Returns `found`, `answer` and `citations`; each citation has the candidate, section, exact passage and its character offsets in the resume |

How it answers:
- **Retrieval:** vector search, chosen by a benchmark (see [Retrieval evaluation](#retrieval-evaluation)).
- **Refusal:** a question whose best match is below 0.25 similarity is answered "Not found in resumes." with no LLM call.
- **Grounding:** the LLM sees only numbered excerpts, and an answer without a valid citation becomes "Not found in resumes.".
- **Fallback:** if Gemini is off or unavailable, you get the cited passages with `summary_unavailable: true` and a reason (`llm_disabled` or `llm_error`), so a client never shows passages as a generated answer.
- **Injection guards:** excerpts sit in a delimited data block (delimiter tags in resume text are stripped) under a "data, not instructions" rule, and replies are parsed strictly. These reduce prompt injection but don't stop it; see [docs/security-injection.md](docs/security-injection.md).
- **Scores:** candidate scores are never read or changed by this endpoint.

### Analytics and health

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/analytics/dashboard` | Counts, average score, score and pipeline distribution, candidates by job, skill gaps |
| `GET` | `/api/analytics/jobs/<id>` | The same metrics for one job, plus a 30-day screening timeline |
| `GET` | `/api/analytics/top-candidates?limit=10` | Highest-scoring candidates |
| `GET` | `/api/health` | Health check |

**Example calls**

```bash
curl -X POST http://127.0.0.1:5000/api/jobs -H "Content-Type: application/json" -d "{\"title\": \"Backend Engineer\", \"description_text\": \"3+ years Python, Django, PostgreSQL. Bachelor's degree.\"}"
```

```bash
curl -X POST "http://127.0.0.1:5000/api/candidates?job_id=1" -F "resume=@sample_resumes/resume_01_ananya_patel.txt"
```

```bash
curl -X POST http://127.0.0.1:5000/api/screen/1/1
```

---

## Retrieval evaluation

A benchmark of 30 recruiter-style questions with 52 hand-checked relevant chunks over 26 synthetic resumes. The protocol (`eval/retrieval_protocol.md`) was frozen and committed before the single measurement run on PostgreSQL + pgvector:

| Configuration | Recall@1 | Recall@5 | Recall@10 | MRR@10 |
|---|---|---|---|---|
| vector | 0.552 | 0.781 | 0.830 | 0.833 |
| bm25 | 0.519 | 0.886 | 0.886 | 0.776 |
| hybrid (RRF) | 0.581 | 0.842 | 0.919 | 0.850 |
| hybrid + reranker | 0.652 | 0.864 | 0.914 | 0.889 |

Neither fusion nor the reranker improved MRR@10 by a statistically reliable margin:
- Hybrid vs vector: +0.017, paired bootstrap 95% CI [−0.071, +0.106].
- Reranker vs hybrid: +0.039, 95% CI [−0.056, +0.133].

So the app uses **vector search**. The full method and per-question results are in [eval/retrieval_results.md](eval/retrieval_results.md), and the not-found threshold in [eval/ask_calibration.md](eval/ask_calibration.md).

---

## Command-line mode

The original CLI agent still ranks a folder of resumes without the web app or database:

```bash
python main.py --jd sample_jd/jd.txt --resumes sample_resumes --output output --no-llm
```

It writes ranked results to `output/ranked_results.json` and `output/ranked_results.csv`.

---

## Testing

```bash
pip install -r requirements-dev.txt
```

```bash
python -m pytest
```

```bash
python -m ruff check .
```

```bash
python -m mypy
```

192 tests across eleven files. No test calls a real LLM or embedding API: the suite fails any test that reaches one instead of using a mocked response.

| File | Tests | What it covers |
|---|---|---|
| [tests/test_agent.py](tests/test_agent.py) | 19 | The original scoring signals, data models and CSV/JSON output |
| [tests/test_platform.py](tests/test_platform.py) | 14 | Database models, duplicate detection, analytics |
| [tests/test_api_contract.py](tests/test_api_contract.py) | 57 | All 25 API routes: responses, validation, errors, unique upload storage, and a sweep checking no route leaks internals |
| [tests/test_concurrency.py](tests/test_concurrency.py) | 1 | 36 concurrent screenings for two jobs with different weights; each uses its own job's weights |
| [tests/test_parsers.py](tests/test_parsers.py) | 25 | Resume and job-description extraction (snapshot), PDF/DOCX reading, the Gemini path with a mocked model |
| [tests/test_llm.py](tests/test_llm.py) | 17 | The Gemini wrapper, model configuration, API-key lookup, rationale text |
| [tests/test_score_regression.py](tests/test_score_regression.py) | 5 | Scores are identical to the original code across 120 cases; per-role weights never leak |
| [tests/test_chunking.py](tests/test_chunking.py) | 26 | Section detection across heading styles, exact offsets, nothing lost or duplicated, chunks fit the model's input |
| [tests/test_embeddings.py](tests/test_embeddings.py) | 11 | The local model for real; the Gemini embedding API mocked |
| [tests/test_indexing.py](tests/test_indexing.py) | 9 | Chunks stored on upload and job changes, reindexing, deletes, a pgvector round trip |
| [tests/test_migrations.py](tests/test_migrations.py) | 8 | Migrated schema matches the models, adoption of older databases, downgrade and upgrade |

Tests marked `slow` load the embedding model; skip them with `python -m pytest -m "not slow"`.

**Running on PostgreSQL.** By default the suite uses a temporary SQLite database and skips the PostgreSQL-only tests. To run everything on PostgreSQL, using the container from [Database setup](#3-database-setup):

```bash
docker exec hireai-pg psql -U hireai -d postgres -c "CREATE DATABASE hireai_test;"
```

```bash
TEST_DATABASE_URL=postgresql+psycopg://hireai:hireai@127.0.0.1:5433/hireai_test TEST_POSTGRES_URL=postgresql+psycopg://hireai:hireai@127.0.0.1:5433/postgres python -m pytest
```

The tests drop and recreate every table, so `TEST_DATABASE_URL` is refused unless the database name contains `test`. `TEST_POSTGRES_URL` is used to create and drop a throwaway database per migration test.

**mypy** runs in strict mode. Modules written before strict typing was adopted are listed in `pyproject.toml` and come off that list as they're typed; new code is never added to it.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Create Job or Upload shows "Could not reach the backend" | Start `python start.py` and open http://127.0.0.1:5000, not the HTML file |
| An uploaded candidate has no score | Click **Score** on that row in Candidates. If it keeps failing, make sure the server was started with `start.py` |
| First scoring after startup is slow | The embedding model is loading; `start.py` loads it before accepting requests |
| "has already been added for this job" | Duplicate detection found the same email, phone or name for that job |
| PDF parses to an empty profile | The PDF is a scanned image with no text layer; use a text-based PDF, DOCX or TXT |
| Port 5000 is in use | Stop the other process, or set `PORT` in `.env` and run `python app.py` |

---

## Limitations

- **Single user, no login.** Anyone who can reach the server can see and change all data. Don't expose it to the internet as-is.
- **Retrieval misses some wordings.** "PhD" vs "Ph.D." and "papers" vs "paper" defeated every method in the benchmark (q19 and q12). A sound fix needs a new question set, because the current one is a frozen test set.
- **Prompt injection is reduced, not solved.** A model can still make a false claim while citing a real passage, and keyword stuffing raises the deterministic skill score (+22.5 points in the injection tests). Details in [docs/security-injection.md](docs/security-injection.md).
- **The not-found floor is weak.** Similarity alone can't separate answerable from unanswerable questions; refusals rely mainly on the LLM's citation check, and only three negative questions have been tried.
- **Small benchmark.** 30 questions over 26 synthetic resumes; confidence intervals are wide. At this size PostgreSQL scans every row instead of using the HNSW index, which is exact.
- **SQLite searches by brute force.** That's fine for hundreds of resumes; use PostgreSQL + pgvector beyond that.
- **Chunking relies on recognizable headings.** A resume without standard section headings (or a PDF whose text extraction loses them) is chunked by paragraph without section labels.
- **Skill extraction without an API key uses a fixed keyword list.** Skills not on that list, and job descriptions that don't use recognizable section headings, can produce fewer required skills. A job with no extracted required skills gives every candidate a full skill score.
- **Scoring templates and interview questions are API-only.** Jobs use the default weights unless a template ID is set through the API.
- **Development server.** Flask's built-in server isn't meant for production traffic.
- **Needs a running server.** The dashboard depends on the Flask backend, so static or serverless hosting (Vercel, Netlify) won't serve a working app.

---

## Responsible AI

HireAI is built to **assist** recruiters, not to make hiring decisions.

- **Job-relevant signals only.** Scores come from resume text similarity, skills, years of experience and education level. Name, gender, age, ethnicity, religion, nationality, marital status and photographs are not scoring inputs.
- **Explainable.** Every score is broken into its four parts, with the exact matched and missing skills, so a recruiter can see why a candidate scored as they did.
- **AI content is labeled.** Written explanations are marked *AI-generated* in the candidate profile.
- **Humans decide.** Pipeline status only changes when a recruiter changes it.
- **Known risks.** Semantic similarity rewards resumes that use similar wording to the job description, and education scoring can disadvantage self-taught candidates. Review low scores before rejecting anyone, and don't use the score as the only filter.
- **Candidate data stays local.** The database and uploaded resumes are stored on your machine and excluded from Git. With a Gemini key set, resume and job text is sent to Google's API, which is why Gemini is for [synthetic data only](#using-gemini-synthetic-data-only).

---

## Project structure

```text
Hire-AI/
├── start.py                  # Recommended entry point: loads model, starts server
├── app.py                    # Flask API + serves the dashboard at /
├── frontend.html             # Recruiter dashboard (Dashboard, Jobs, Candidates, Analytics)
├── models.py                 # Typed SQLAlchemy models, incl. ResumeChunk/JobChunk with embeddings
├── database.py               # Engine creation; applies Alembic migrations on startup
├── chunking.py               # Section-aware chunking with exact source offsets
├── embeddings.py             # Pluggable embedding providers (Sentence-Transformers, Gemini)
├── indexing.py               # Chunk + embed on save; `python -m indexing --reindex`
├── analytics_service.py      # Metrics computed from database records
├── duplicate_detection.py    # Email / phone / fuzzy-name duplicate checks
├── interview_generator.py    # Candidate-specific interview questions
├── scorer.py                 # Four-signal scoring engine (original)
├── resume_parser.py          # Resume extraction (original)
├── jd_parser.py              # Job description extraction (original)
├── ranker.py                 # Ranking and explanations for the CLI (original)
├── config.py                 # Default weights, model names, data classes, .env loading
├── llm.py                    # The single place that calls Gemini (google-genai SDK)
├── main.py                   # CLI entry point (original)
├── utils.py                  # File discovery and CSV/JSON output
├── scoring_method.md         # Scoring methodology in detail
├── requirements.txt          # Runtime dependencies
├── requirements-dev.txt      # + pytest, coverage, ruff, mypy
├── pyproject.toml            # ruff, mypy and pytest settings
├── alembic.ini
├── migrations/               # Alembic environment and schema revisions
├── .env.example
├── docs/
│   ├── demo.gif
│   ├── screenshots/          # dashboard, jobs, candidates, analytics
│   └── phase-N-notes.md      # Design notes for each upgrade phase
├── sample_jd/                # Sample job description
├── sample_resumes/           # 12 synthetic sample resumes
├── output/                   # Sample CLI output
└── tests/
    ├── fixtures/             # Score baseline, parser snapshot, extra job description
    ├── test_agent.py
    ├── test_platform.py
    ├── test_api_contract.py
    ├── test_concurrency.py
    ├── test_parsers.py
    ├── test_llm.py
    ├── test_score_regression.py
    ├── test_chunking.py
    ├── test_embeddings.py
    ├── test_indexing.py
    └── test_migrations.py
```

---

## License

MIT. See [LICENSE](LICENSE).
