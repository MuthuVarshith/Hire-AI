# "Not found in resumes": threshold calibration

`ask.py` refuses an answer through two gates. This note records how the first gate's threshold was set, and how both gates behaved on live Gemini calls. All data is synthetic.

## Gate 1: retrieval similarity floor

Top-1 cosine similarity from vector search (`all-MiniLM-L6-v2`, exact search on SQLite, 26 synthetic resumes):

| Group | Questions | Top-1 similarity |
|---|---|---|
| Unanswerable (negatives) | n01, n02, n03 | 0.359, **0.248**, 0.487 |
| Answerable (benchmark) | q01–q30 | min **0.277** (q19), median ≈ 0.51, max 0.837 |

The two groups overlap: n03 (0.487) scores above 10 of the 30 answerable questions. A threshold above 0.487 would refuse a third of the real questions, so similarity can't be the main gate.

**Chosen: 0.25.** This is a floor that drops only clearly off-topic questions; it refuses n02 and no answerable question.

**Caveats:**
- The answerable scores come from the frozen test set, so checking the floor against them is mild exposure to it. Only one number was chosen, and it was set to sit below every answerable question rather than to optimize a metric.
- Three negative questions are far too few to estimate a false-answer rate.

## Gate 2: grounding (live Gemini, `gemini-3.8-flash`, one run)

| Question | Gate that decided | Result |
|---|---|---|
| n01 (COBOL) | grounding | "Not found in resumes." |
| n02 | similarity floor (no LLM call) | "Not found in resumes." |
| n03 | grounding | "Not found in resumes." |
| q05 (OSCP and CISSP) | — | Correct, 2 valid citations |
| q16 (vector databases) | — | Sophia Nguyen and Javier Lopez, correctly cited. Aarav's FAISS project wasn't retrieved, so the answer omits him |
| q23 | — | Gemini returned 503 after all retries, which led to the passages-only fallback |

This is a spot check, not a measurement. A real faithfulness and refusal evaluation (golden set, RAGAS, LLM-as-judge) is planned for Phase 4.
