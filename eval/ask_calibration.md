# "Not found in resumes": threshold calibration

`ask.py` refuses an answer through two gates. This note records how the first gate's threshold was set. All data is synthetic.

## Gate 1: retrieval similarity floor

Top-1 cosine similarity from vector search (`all-MiniLM-L6-v2`, exact search on SQLite, 26 synthetic resumes, the retrieval configuration in `ask.CHOSEN_CONFIG`). Regenerate with:

    python -m eval.ask_similarity

No LLM is called. Output of that script:

| Group | Questions | Top-1 similarity |
|---|---|---|
| Unanswerable (negatives) | n01, n02, n03 | 0.359, **0.248**, 0.487 |
| Answerable (benchmark) | q01–q30 (n=30) | min **0.277** (q19), median 0.512, max 0.837 (q05) |

The two groups overlap: n03 (0.487) scores above 11 of the 30 answerable questions. A threshold above 0.487 would refuse more than a third of the real questions, so similarity can't be the main gate.

**Chosen: 0.25, PROVISIONAL.** It is a floor that drops only clearly off-topic questions; on this data it refuses n02 and no answerable question.

**Why it is provisional:**
- It was chosen with only 3 negative questions, far too few to estimate a false-answer rate.
- The answerable and unanswerable distributions overlap, so no cutoff separates them; 0.25 sits just under the lowest answerable score (0.277) and only 0.002 above n02 (0.248).
- The answerable scores come from the frozen retrieval test set, so checking the floor against them is mild exposure to it. Only one number was chosen, set below every answerable question rather than to optimize a metric.
- It will be recalibrated in Phase 4 on a held-out set with more negatives.

## Gate 2: grounding

Questions that pass the floor go to the LLM, whose answer must cite excerpts it was given; an answer with no valid citation becomes "Not found in resumes." This gate is covered by mocked-LLM tests in `tests/test_ask.py`. Live Gemini results are produced by `eval/ask_live.py` and recorded separately (owned by the live-evaluation work, not this note).

### Previous informal check (superseded, not a measurement)

An earlier one-off run against live Gemini, kept only for history. It is not reproducible from this repository and must not be quoted as a result; see the live results file instead.

| Question | Gate that decided | Result |
|---|---|---|
| n01 (COBOL) | grounding | "Not found in resumes." |
| n02 | similarity floor (no LLM call) | "Not found in resumes." |
| n03 | grounding | "Not found in resumes." |
| q05 (OSCP and CISSP) | — | Correct, 2 valid citations |
| q16 (vector databases) | — | Sophia Nguyen and Javier Lopez, correctly cited. Aarav's FAISS project wasn't retrieved, so the answer omits him |
| q23 | — | Gemini returned 503 after all retries, which led to the passages-only fallback |

A real faithfulness and refusal evaluation (golden set, RAGAS, LLM-as-judge) is planned for Phase 4.
