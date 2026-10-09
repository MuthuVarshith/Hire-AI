# Ask the candidate pool: live check (attempt 1, blocked by quota)

Run on 2026-10-09 at commit `de11f27`, model `gemini-3.8-flash` (config.GEMINI_MODEL), via
`python -m eval.ask_live`: POST /api/ask on the Flask test client, throwaway SQLite database,
26 synthetic benchmark resumes indexed with `indexing.index_candidate`, ASK_LLM_ENABLED=true,
sentence-transformers embeddings, at least 6 s between questions. Raw output: `eval/ask_live_results.json`.

## Outcome

The run produced **no generated answers**. Every Gemini call failed with
`429 RESOURCE_EXHAUSTED`: the free-tier daily quota (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`,
limit 20 requests/day for gemini-3.8-flash) was already used up before the run started; the error
asked to retry in about 14h42m. The existing retry logic retried and then gave up, as designed.
The run was not repeated (one run only, and the quota had not reset).

Counts from `ask_live_results.json` (33 questions):

| outcome | count |
|---|---|
| correct / partially correct / wrong (judged answers) | 0 / 0 / 0 (nothing to judge) |
| "Not found" (retrieval floor, no LLM call) | 1 (n02, top similarity 0.248) |
| passages-only fallback, `summary_unavailable_reason = llm_error` | 32 (q01-q30, n01, n03) |
| HTTP errors | 0 (all 33 returned 200) |

The 32 fallbacks are correct behaviour of the route: it returned the 8 retrieved passages with
`summary_unavailable=true`. No correctness or citation-support judgements could be made; each row's
`judgement` field says so. 33 questions is too small to estimate rates reliably even when the run succeeds.

## What the passages-only results still show (retrieval, not answer quality)

- n01 (COBOL, 0.359) and n03 (Salesforce, 0.487) passed the 0.25 floor, so without the LLM they
  would show 8 passages rather than "Not found"; only n02 was refused. The floor alone does not stop negatives.
- q12 (published papers, top 0.295) and q19 (PhD, 0.277) sit just above the floor and none of the
  8 returned passages is a labelled chunk, so even a working LLM would likely answer "not found" or wrongly.
- q16 (vector DB / semantic search): 3 of 8 passages are labelled chunks.
- q23 (feature flags / trunk-based development, 0.317): 2 labelled chunks retrieved.

## Bugs / issues

- `llm.py:27` `_is_transient` treats every 429 as transient, including daily-quota exhaustion
  (`retryDelay` ~52936 s). Each question then spent the full retry budget (`llm.py:21`, 2+5+10 s,
  plus the SDK's own tenacity retries) on a request that could not succeed. The route still degraded correctly.

## To re-run

After the quota resets (or on a paid key): `python -m eval.ask_live --env-file C:/Hire-AI/.env`.
33 questions exceed a 20/day free quota, so a full run needs either a paid tier or two days.
