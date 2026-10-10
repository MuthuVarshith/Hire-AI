# Ask the candidate pool: live check, batch 1 (q01–q16)

Run on 2026-10-10 through `POST /api/ask` on the Flask test client, with a throwaway SQLite database and the 26 synthetic benchmark resumes. Model `gemini-3.8-flash`, free tier, at least 6 s between questions. Raw output: `eval/ask_live_batch1.json`.

**Commit `e80b3df`.** The results file first recorded `0335c84`: this run used the older runner, which read HEAD at the end, and three builder commits landed while it ran. The run started one second after `e80b3df`, and no file `/api/ask` uses changed before it ended. Later runs record the commit at the start and refuse to run with uncommitted changes in that code or its inputs.

## Outcome

| Outcome | Questions | Count |
|---|---|---|
| Generated answer | q01, q03–q09 | 8 |
| Passages only: 503 after retries | q02 | 1 |
| Passages only: daily quota of 20 exhausted (429) | q10–q16 | 7 |

All 16 returned HTTP 200. Every passages-only response set `summary_unavailable=true` with reason `llm_error`.

**Requests: 19 to 43, not exactly known.** This run predates the per-request counter, and `llm.py` retried transient errors without logging them. The Gemini SDK does not retry on its own here, so each `llm.py` attempt was one request.

| Questions | Requests |
|---|---|
| q02 | 4, exactly: the first try and 3 retries, all 503 |
| q10–q16 | 1 each, exactly: the daily-quota 429 is not retried |
| q01, q03–q09 | 1 to 4 each: a 503 followed by a success is not logged |

At least 12 requests were made before the quota ran out at q10. An earlier version of this note said "at most 12"; that ignored retries that ended in success. Since then, a 5xx is retried at most once, and later runs count every request.

## Answer quality (8 generated answers)

These are the opinion of the checking model (Claude Opus 5.5), not a metric:

- **Correct (6):** q03, q04, q05, q07, q08, q09.
- **Partly correct (2):**
  - q01 missed one of the two labelled candidates.
  - q06 missed one of the two labelled candidates and misread "11 engineers" across two teams as two teams of 11.
- **Wrong:** none.

Every answer cited at least one labelled chunk, and every citation supports the claim attached to it. The misses are omissions, not invented claims.

Eight answers are far too few to estimate a rate.

## Still to run

The free tier allows 20 requests a day and no paid key will be used. The remaining questions are:

- q02, q10–q16 (they hit the quota or a 503)
- q17–q30 and n01–n03 (batch 2)

That is 25 questions and 24 requests (n02 falls below the similarity cutoff and makes no request), so they need two more days.
