# Phase 1 notes: data layer, migrations and section-aware chunking

Phase 1 had two parts: first the three fixes you asked for from Phase 0's findings, then the data layer that retrieval (Phase 2) builds on.

## What was built

| Area | Change |
|---|---|
| **Resume-overwrite fix** | Uploads are stored as `<uuid4>_<sanitized name><extension>`. Two same-named uploads can no longer share a file, and non-ASCII names (e.g. `резюме.pdf`) keep their extension, so PDFs are still read as PDFs |
| **Orphaned files** | Deleting a job now deletes its candidates' resume files, after the database commit succeeds |
| **No leaked internals** | Every error response is generic; the full message and traceback go to the server log only. Duplicate template names return 409 instead of a 500 containing SQL. Non-JSON and oversized requests return 415 and 413 instead of 500 |
| **Concurrency test** | 36 concurrent screenings for two jobs with opposite weights; every score uses its own job's weights |
| **Typed models** | SQLAlchemy 2.0 `Mapped[...]` style, with no schema change (fingerprint identical) |
| **PostgreSQL + pgvector** | One database for records and vectors; SQLite still works for local use and tests |
| **Alembic** | Baseline migration for the existing schema plus one for chunk tables; applied on startup; older databases adopted without recreation |
| **Section-aware chunking** | Resumes and job descriptions split by section (Summary, Experience, Projects, Skills, Education…), with exact source offsets |
| **Embedding providers** | Pluggable: Sentence-Transformers (default, offline) or the Gemini embedding API |
| **Indexing** | Chunks embedded and stored on upload, job creation and description edits; `python -m indexing --reindex` rebuilds them |

**Results:**
- 192 tests pass, up from 126, and **all 192 also pass on PostgreSQL 17 with pgvector**.
- The 120-case score-equality test passes at **every one of the 10 commits**, each checked out on its own. Scores are unchanged throughout.
- A fresh virtual environment, installed only from `requirements-dev.txt`, picked up newer libraries than development used (SQLAlchemy 2.1.4 instead of 2.0.36, torch 2.14). ruff, strict mypy and the full suite pass there too.
- ruff and strict mypy are clean.
- Coverage of application code rose from 81% to 86%. The new modules are at 96–100%: `chunking.py` 99%, `indexing.py` 97%, `embeddings.py` 96%, `database.py` 100%.
- The mypy exemption list shrank from 13 modules to 11.

## Commits

| Commit | Change |
|---|---|
| `1e63bea` | Store uploads under unique names so resumes can't overwrite each other |
| `372fa77` | Delete candidates' resume files when their job is deleted |
| `d873b42` | Stop leaking exception text, SQL and paths in API error responses |
| `1920a6c` | Add API-level concurrency test for per-job scoring weights |
| `b7ffef0` | Rewrite models in SQLAlchemy 2.0 typed style with no schema change |
| `be4cb06` | Add section-aware chunking for resumes and job descriptions |
| `154b4d7` | Add pluggable embedding providers for retrieval |
| `68a25c3` | Manage the schema with Alembic; adopt databases created before migrations |
| `dd0db53` | Store chunked, embedded resumes and job descriptions for retrieval |
| `ade2508` | Declare PostgreSQL dependencies; allow running the suite on PostgreSQL |
| (this commit) | README updates and these notes |

## Proving the fixes have teeth

A test that passes on the fixed code proves little unless it would **fail** on the broken code. For each fix, the old behavior was temporarily restored and the new test was run against it:

| Fix | Old behavior restored | Result |
|---|---|---|
| Unique upload names | Timestamp naming, frozen to one second | Both regression tests fail |
| No leaked internals | Handlers returning `str(e)` again | The sweep test fails on the first route |
| Per-job weights | The shared `WEIGHTS` dict overwritten per request | Failed in **5 of 5 runs**, with 5 to 10 of 36 concurrent scores using the other job's weights |

The last row is also the first direct evidence that the race in the original code was real, not theoretical.

## Design decisions and why

### 1. PostgreSQL + pgvector instead of a separate vector database
Candidate records and their embeddings live in one database:
- **One consistent state:** a candidate and their chunks commit or fail together.
- **Simple deletion:** deleting a candidate cascades to their vectors, which matters for removing personal data.
- **Hybrid search in SQL:** the Phase 2 combination of vector similarity, keyword search and filters is one query.
- **Less to run:** one service locally and in deployment.

The trade-off is scale: dedicated vector stores go further, into many millions of vectors, which a recruiting tool won't approach.

### 2. Typed models before migrations, with a fingerprint as proof
Rewriting the models changes how every column is declared, so "nothing changed" needed evidence. Before the rewrite I captured a fingerprint:
- the `CREATE TABLE` SQL for both SQLite and PostgreSQL;
- every Python-side default and update value;
- all 10 relationships with their cascades.

After the rewrite, all four were identical. Only then was the Alembic baseline generated, so the baseline describes the real, unchanged schema.

### 3. Adopting existing databases instead of recreating them
A database created by an earlier version has the four tables but no Alembic history. On startup the app detects that case, records it as already at the baseline ("stamping"), and applies only newer migrations. Nothing is dropped, and a test proves the data survives. The alternative of dropping and recreating, or asking users to run a manual command, risks losing candidate data.

### 4. One embedding column type, two databases
`EmbeddingVector` is pgvector's `vector` on PostgreSQL and a JSON array on SQLite. The column has **no fixed dimension**, and every row stores the name of the model that made it, for three reasons:
- Switching providers (384-dimension local model, 768-dimension Gemini) doesn't need a schema change.
- Vectors from different models are never compared by accident.
- Migrations don't depend on a setting.

The cost: pgvector's fast HNSW index needs a fixed dimension. Phase 2 will add a per-model partial index (on `embedding::vector(384)` where the model matches) when real search queries exist to design it around.

### 5. Chunks keep exact offsets
Every chunk satisfies `source[start:end] == text`. Phase 2's answers must cite the exact resume passage they used, and offsets make that a guarantee rather than a fuzzy match. A test checks on all 14 sample documents that every character of content lands in exactly one chunk, with nothing lost or duplicated.

### 6. Headings from a vocabulary, not guesswork
Section headings are matched against a fixed list per document type, written in many styles: ALL CAPS, `## Markdown`, `=== decorated ===`, inline `Skills: …`, or with a trailing `(qualifier)`. Guessing that "any short capitalized line is a heading" would misfire on candidate names and company lines. The trade-off: a resume with unusual headings gets paragraph chunks without section labels. Content is never lost, but the section label is.

### 7. Chunk size is checked against the real tokenizer
`all-MiniLM-L6-v2` silently truncates input at 256 tokens. I first assumed 800 characters would always fit; a test with the real tokenizer showed **800 characters of tool names come to 310 tokens**, so the end of a skills list would never have been embedded. Skills are exactly what recruiters search for. Now whoever embeds supplies a "fits" check using the model's own tokenizer, and the chunker splits further until every chunk fits.

### 8. Embedding never blocks saving
Indexing runs **after** the upload or job is committed. If the model or API fails, the record is still saved, chunks are stored without vectors, and `--reindex` fills them in later. Losing a candidate because an embedding call failed would be the wrong trade.

## Trade-offs

| Choice | Benefit | Cost |
|---|---|---|
| pgvector in PostgreSQL | One consistent store; simple deletion; hybrid search in SQL | Less headroom than a dedicated vector database |
| Dimension-free vector column | Swap providers without migrations | The HNSW index must be a per-model partial index (Phase 2) |
| Vocabulary-based headings | Never mistakes names for headings | Unusual headings lose their section label |
| Indexing after commit | Uploads never fail because of embeddings | A short window where a candidate has no vectors |
| Migrations on startup | Nothing to remember when upgrading | Multiple app instances starting at once would race; production deploys should run `alembic upgrade head` as a separate step (Phase 6) |
| SQLite still supported | Zero-setup local use and fast tests | Brute-force vector search only |

## Still open

| Item | Where it goes |
|---|---|
| Vector index (HNSW) and search queries | Phase 2 |
| Request validation (non-text status still returns 500), 405 as JSON | Phase 5 |
| `sort_by=score` drops unscored candidates | Phase 5 |
| Empty rationale when Gemini fails | Phase 3 |
| The 12 sample resumes all use the same four headings and none has a Projects section; the chunker's broader formats are tested only with synthetic resumes | Phase 4 golden dataset should include varied real-world formats |
| `main.py` and `start.py` have no tests | — |

## Interview questions you should be able to answer

**1. "Why pgvector rather than Pinecone or Weaviate?"**
A strong answer covers:
- **The data:** candidates and their embeddings must stay consistent. One transaction covers both, and deleting a candidate deletes their vectors, which matters for personal data.
- **The queries:** Phase 2 needs vector similarity, keywords and relational filters together, which is a single SQL query.
- **The scale:** a recruiting tool holds thousands, not millions, of resumes, well within pgvector's range.
- **When you'd switch:** much larger scale, or managed features a dedicated store offers. Name what would trigger it rather than claiming one is always better.

**2. "How did you make sure the migration didn't change the schema, and how do existing users upgrade?"**
- Fingerprinted the schema (CREATE TABLE SQL for two databases, defaults and relationships) before and after the typed-models rewrite; identical.
- Generated the baseline only after that, so it matches reality.
- A test runs Alembic's own comparison between the migrated database and the models (no differences), on SQLite and PostgreSQL.
- Existing databases are detected and stamped, not recreated; a test proves their data survives.
- Downgrade-then-upgrade is tested. It caught that PostgreSQL keeps an enum type after its table is dropped, which would have broken re-upgrading.

**3. "How did you choose your chunk size?"**
- The embedding model truncates input at 256 tokens, so a chunk must be embedded whole or its tail is silently lost.
- The first assumption (800 characters is always safe) was **tested and was wrong**: dense lists of tool names measured 310 tokens.
- Rather than guessing a smaller number, the chunker takes a fits check from the embedding side and splits until every chunk passes the model's own tokenizer. The character limit is just a first pass.
- Sections bound chunks too, so a chunk never mixes Experience with Education, which keeps citations meaningful.
