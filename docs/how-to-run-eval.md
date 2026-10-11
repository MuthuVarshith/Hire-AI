# How to run the answer evaluation

The method is fixed in [`eval/answer_eval_protocol.md`](../eval/answer_eval_protocol.md), including its dated deviations. This page lists the commands in order. **Only the 26 synthetic resumes in `sample_resumes/` are ever sent to an LLM.** Never point these scripts at real candidates' data.

`eval/ask_live.py` needs the FastAPI app (`app/main.py`), so the ask batches can run only after that is merged.

## 0. Setup

```bash
pip install -r requirements-eval.txt     # ragas, langfuse; the app's requirements come with it
python -m eval.golden validate           # must pass before any run
```

Keys go in `.env` (gitignored) or the environment, never in a commit:

| Variable | Used by | Notes |
|---|---|---|
| `GOOGLE_API_KEY` | ask batches (Gemini writes the answers) | free tier |
| `OPENROUTER_API_KEY` | the judge (default provider) | free account at openrouter.ai |
| `JUDGE_PROVIDER` | the judge | `openrouter` (default) or `gemini` |
| `JUDGE_MODEL` | the judge | default `meta-llama/llama-3.3-70b-instruct:free` |

Free OpenRouter model IDs come and go. Before the first judge run, check the default is still listed at <https://openrouter.ai/models?max_price=0>. If it isn't, set `JUDGE_MODEL` to another free instruct model that isn't a Gemini model, and keep it for the whole evaluation. Some free models require allowing prompt logging in OpenRouter's privacy settings; that is acceptable only because the data is synthetic.

Every script that sends requests refuses to start with uncommitted changes in its code or inputs, and records the commit. Commit first.

## Daily request budgets

| Service | Free limit | Spent on |
|---|---|---|
| Gemini `gemini-3.8-flash` | **20 requests a day** | the ask batches only (24 requests left) |
| OpenRouter free models | when this was written: 20 a minute, and 50 a day (1000 a day after buying at least 10 credits). **Check the current limits** at <https://openrouter.ai/docs/api-reference/limits> | the judge: 40 judge-check plus at most 33 benchmark requests in combined mode |

Retries count against these limits, and every script counts each HTTP request, retries included.

## 1. Ask batches (Gemini)

Run batch 2 on one day and batch 3 on another (or later, if a batch hits the quota):

```bash
python -m eval.ask_live --env-file .env --ids q02,q10,q11,q12,q13,q14,q15,q16,q17,q18,q19,q20,q21,q22,q23,q24 --out eval/ask_live_batch2.json
python -m eval.ask_live --env-file .env --ids q25,q26,q27,q28,q29,q30,n01,n02,n03 --out eval/ask_live_batch3.json
```

Batch 2 is 16 questions (16 requests before retries); batch 3 is 9 (n02 is refused by the similarity floor and makes none). Each file records the commit, `gemini_requests_total` and each row's `gemini_requests`. Commit each batch file after its run.

**Resume:** a question that fell back to passages (`summary_unavailable: true`, for example after the daily quota ran out) has no generated answer. Re-run just those ids on a later day into the next batch number, for example `--ids q20,q21 --out eval/ask_live_batch4.json`. The first generated row in batch-number order is the one judged, so earlier rows are never replaced.

## 2. Metrics with no LLM

```bash
python -m eval.evaluate                  # eval/results/evaluate.json
```

## 3. Judge (OpenRouter by default)

See what is left and what it costs (no requests):

```bash
python -m eval.judge plan
```

Judge check first, then the benchmark. Set `--max-requests` to what is left of the day's limit:

```bash
python -m eval.judge run --set judge-check --max-requests 40 --env-file .env
python -m eval.judge run --set benchmark --max-requests 33 --env-file .env
```

The default `--mode combined` sends one request per answer. `--mode ragas` is the original four requests per answer (RAGAS faithfulness 2, RAGAS relevancy 1, rubric 1); pick one mode before starting and use it for every `run`, `plan` and `summarize`.

**Resume:** just run the same command again on a later day. Each finished item is cached in `eval/results/judge/`, keyed by item, answer, mode, judge provider and model, and prompt hash, so cached items are skipped. A run stops cleanly between items when the budget would be exceeded; a call that fails after retries is not cached and is retried next time. Each run appends its request count to `eval/results/judge_runs.jsonl`.

Then:

```bash
python -m eval.judge summarize           # eval/results/judge_summary.json
```

## 4. Cutoff recalibration (no LLM)

Only after ask batches 2 and 3, so every judged answer comes from the 0.25 cutoff:

```bash
python -m eval.cutoff                    # eval/results/cutoff.json, a proposal only
```

`ask.NOT_FOUND_THRESHOLD` changes only in a separate commit after the owner reviews the proposal.

## 5. Report

```bash
python -m eval.report                    # eval/report.md
```

The report copies numbers from `eval/results/*.json` only and shows "not yet measured" for anything missing.

## Where results go

| File | Written by |
|---|---|
| `eval/ask_live_batchN.json` | `eval.ask_live` |
| `eval/results/evaluate.json` | `eval.evaluate` |
| `eval/results/judge/<set>/*.json` | `eval.judge run` (one file per item and metric) |
| `eval/results/judge_runs.jsonl` | `eval.judge run` (one line per run) |
| `eval/results/judge_summary.json` | `eval.judge summarize` |
| `eval/results/cutoff.json` | `eval.cutoff` |
| `eval/report.md` | `eval.report` |
