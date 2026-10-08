# Retrieval evaluation protocol (frozen before measurement)

This file is committed **before** any measurement is run, so the method can't be adjusted to fit the results.

## Setup
- **Corpus:** the 26 synthetic resumes in `sample_resumes/*.txt` and `sample_resumes/varied/v*`, chunked by the current `chunking.py` (one chunk per job in experience sections).
- **Labels:** `eval/retrieval_benchmark.json`, as approved: 30 questions, 52 labelled chunks, plus the written labelling rules. The 3 negative questions are excluded from these metrics; they are for calibrating a "not found" threshold later.
- **Database:** a fresh PostgreSQL 17 + pgvector database, created and migrated for the run, so vector search goes through the HNSW index exactly as in production. SQLite is not measured; it uses exact brute-force search, so results there can only match or exceed HNSW recall.
- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2`, local. No resume text leaves the machine.
- **Search scope:** the whole candidate pool (no job filter).

## Configurations
| Name | Vector | BM25 | Fusion | Reranker |
|---|---|---|---|---|
| `vector` | yes | no | — | no |
| `bm25` | no | yes | — | no |
| `hybrid` | yes | yes | RRF, k = 60 | no |
| `hybrid+rerank` | yes | yes | RRF, k = 60 | `cross-encoder/ms-marco-MiniLM-L-6-v2` over the top 50 |

Each method contributes its top 50 chunks (`pool = 50`); every configuration returns its top 10.

## Metrics (per question, then averaged over the 30)
- **Recall@k** for k = 1, 5, 10: labelled chunks found in the top k, divided by the number of labelled chunks. For a question with several labels, Recall@1 can't reach 1, so the report also states the best achievable Recall@1.
- **MRR@10:** 1 / rank of the first labelled chunk in the top 10, or 0 if none appears.

## Decision rule (keep a component only if it measurably helps)
A component is kept if adding it improves **MRR@10 by at least 0.02** over the configuration without it **and** a paired bootstrap (10,000 resamples of the 30 questions, fixed seed 0) gives a 95% confidence interval for that difference that **excludes 0**. The comparisons:
1. `hybrid` vs the better of `vector` and `bm25`: is fusion worth it?
2. `hybrid+rerank` vs `hybrid`: is the reranker worth it?

If neither combination clears the bar, the simplest configuration with the highest MRR@10 is chosen. Recall@5 is reported alongside as a secondary check, but it doesn't decide.

## Rules for the run
- The run happens once, and the numbers are reported as produced.
- These 30 questions are now a **test set**. No parameter (pool size, RRF k, reranker depth, chunk size) will be tuned against them after the run. Any later tuning needs a separate, new set of questions.
- Results are written to `eval/retrieval_results.json` and `eval/retrieval_results.md`, along with the commit hash and library versions.
