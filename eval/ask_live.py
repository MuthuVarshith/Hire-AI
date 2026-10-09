"""Live check of Ask the candidate pool on the 30 benchmark questions plus the 3 negatives.

    python -m eval.ask_live

Indexes the synthetic benchmark resumes (eval.benchmark.corpus_files) into a temporary SQLite
database, turns the LLM on, and calls ask.answer_question once per question, sequentially, with at
least PACING_SECONDS between Gemini calls (free tier). Only synthetic resumes are sent to Gemini.
Writes eval/ask_live_results.json and eval/ask_live_results.md. A spot check, not a rate estimate.
"""
import datetime
import json
import os
import subprocess
import time
from typing import Any

from eval.benchmark import ROOT, load
from eval.pool import indexed_pool, labelled_chunk_ids

PACING_SECONDS = 6.0
RESULTS_JSON = ROOT / "eval" / "ask_live_results.json"
RESULTS_MD = ROOT / "eval" / "ask_live_results.md"


def run() -> dict[str, Any]:
    import ask
    import config
    import llm
    from embeddings import SentenceTransformerProvider
    from models import Candidate, ResumeChunk

    api_key = config.get_api_key()
    if not api_key:
        raise SystemExit("no Gemini API key configured")
    os.environ["ASK_LLM_ENABLED"] = "true"

    last_call = [0.0]
    errors: list[str] = []

    def paced_generate(prompt: str, key: str) -> str:
        wait = PACING_SECONDS - (time.monotonic() - last_call[0])
        if wait > 0:
            time.sleep(wait)
        try:
            return llm.generate_text(prompt, key)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {str(exc)[:200]}")
            raise
        finally:
            last_call[0] = time.monotonic()

    benchmark = load()
    questions = [dict(q, kind="positive") for q in benchmark["questions"]]
    questions += [dict(q, kind="negative", relevant=[]) for q in benchmark["negative_questions"]]
    rows = []
    provider = SentenceTransformerProvider()
    with indexed_pool(provider) as session:
        files: dict[int, str] = {cid: str(fn) for cid, fn in session.query(Candidate.id, Candidate.resume_filename)}
        for q in questions:
            labelled = {(c.candidate_id, c.char_start) for c in
                        session.query(ResumeChunk).filter(ResumeChunk.id.in_(labelled_chunk_ids(session, q)))}
            errors.clear()
            result = ask.answer_question(session, q["question"], provider, api_key=api_key,
                                         generate=paced_generate)
            cited = [(files[c.candidate_id], c.section) for c in result.citations]
            rows.append({
                "id": q["id"], "kind": q["kind"], "question": q["question"], "found": result.found,
                "generated": result.generated, "summary_unavailable": result.summary_unavailable,
                "summary_unavailable_reason": result.summary_unavailable_reason,
                "top_similarity": None if result.top_similarity is None else round(result.top_similarity, 4),
                "cited": cited,
                "labelled_citation": any((c.candidate_id, c.char_start) in labelled for c in result.citations),
                "llm_errors": list(errors), "answer": result.answer,
            })
            print(f"{q['id']}: found={result.found} generated={result.generated} "
                  f"unavailable={result.summary_unavailable_reason} errors={len(errors)}", flush=True)

    pos = [r for r in rows if r["kind"] == "positive"]
    neg = [r for r in rows if r["kind"] == "negative"]
    counts = {
        "negatives": len(neg),
        "negatives_refused": sum(not r["found"] for r in neg),
        "positives": len(pos),
        "positives_answered_generated": sum(r["found"] and r["generated"] for r in pos),
        "positives_answered_with_labelled_citation": sum(r["found"] and r["generated"] and r["labelled_citation"]
                                                         for r in pos),
        "positives_not_found": sum(not r["found"] for r in pos),
        "summary_unavailable_llm_error": sum(r["summary_unavailable_reason"] == "llm_error" for r in rows),
        "questions_with_llm_errors": sum(bool(r["llm_errors"]) for r in rows),
    }
    return {
        "model": config.GEMINI_MODEL,
        "date": datetime.date.today().isoformat(),
        "commit": subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip(),
        "pacing_seconds": PACING_SECONDS, "threshold": ask.NOT_FOUND_THRESHOLD,
        "counts": counts, "results": rows,
    }


def markdown(r: dict[str, Any]) -> str:
    c = r["counts"]
    lines = [
        "# Ask the candidate pool: live check",
        "",
        f"One sequential run on {r['date']} at commit `{r['commit']}`, model `{r['model']}`, "
        f"similarity floor {r['threshold']}, at least {r['pacing_seconds']:.0f} s between Gemini calls. "
        f"Synthetic resumes only (26 benchmark resumes, SQLite exact search).",
        "",
        f"- Negatives refused (\"Not found\"): **{c['negatives_refused']} / {c['negatives']}**",
        f"- Positives answered with a generated, cited answer: **{c['positives_answered_generated']} / "
        f"{c['positives']}**",
        f"- ... of which cite at least one labelled chunk: **{c['positives_answered_with_labelled_citation']}**",
        f"- Positives refused as not found: **{c['positives_not_found']}**",
        f"- Passages-only fallback after an LLM error: **{c['summary_unavailable_llm_error']}** "
        f"(questions with any Gemini error recorded: {c['questions_with_llm_errors']})",
        "",
        "33 questions is far too small for a reliable rate; treat these as counts from one run, not estimates.",
        "A labelled citation means the answer cites at least one chunk the benchmark labels for that question; "
        "it does not check that the answer text is faithful.",
        "",
        "| id | found | generated | summary unavailable | top sim | labelled cite | cited (resume, section) |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in r["results"]:
        cited = "; ".join(f"{res} ({sec})" for res, sec in row["cited"]) or "-"
        lines.append(f"| {row['id']} | {row['found']} | {row['generated']} | "
                     f"{row['summary_unavailable_reason'] or '-'} | {row['top_similarity']} | "
                     f"{row['labelled_citation']} | {cited} |")
    lines += ["", "## Answers", ""]
    for row in r["results"]:
        lines.append(f"- **{row['id']}** {row['question']}  \n  {' '.join(row['answer'].split())}")
        for err in row["llm_errors"]:
            lines.append(f"  - Gemini error: `{err}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    result = run()
    RESULTS_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    RESULTS_MD.write_text(markdown(result), encoding="utf-8")
    print(json.dumps(result["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
