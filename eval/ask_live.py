"""Live check of Ask the candidate pool on the 30 benchmark questions plus the 3 negatives.

    python -m eval.ask_live [--env-file PATH]

Goes through the real route: POST /api/ask on the Flask test client, against an app whose
DATABASE_URL is a throwaway SQLite file. The 26 synthetic benchmark resumes (eval.benchmark.corpus_files)
are indexed with indexing.index_candidate exactly as eval/pool.py does, ASK_LLM_ENABLED=true is set in
this process only, and questions run sequentially with at least PACING_SECONDS between them (free tier).
Only synthetic resumes are sent to Gemini. The API key is read from GOOGLE_API_KEY, or from --env-file
into this process's environment; it is never printed or written.

Writes eval/ask_live_results.json (raw API output plus label matching). Judgements of correctness are
added afterwards by hand under each row's "judgement" key; they are not computed here.
A spot check, not a rate estimate.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from eval.benchmark import ROOT, corpus_files, load, resume_key

PACING_SECONDS = 6.0
RESULTS_JSON = ROOT / "eval" / "ask_live_results.json"


def _load_key(env_file: str | None) -> None:
    if os.environ.get("GOOGLE_API_KEY") or not env_file:
        return
    for line in Path(env_file).read_text(encoding="utf-8").splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() == "GOOGLE_API_KEY":
            os.environ["GOOGLE_API_KEY"] = value.strip().strip('"').strip("'")


def run(env_file: str | None) -> dict[str, Any]:
    tmp = tempfile.mkdtemp(prefix="ask_live_")
    os.environ["DATABASE_URL"] = f"sqlite:///{(Path(tmp) / 'ask_live.db').as_posix()}"
    os.environ["ASK_LLM_ENABLED"] = "true"
    os.environ["EMBEDDING_PROVIDER"] = "sentence-transformers"  # the frozen retrieval choice
    _load_key(env_file)

    import app as app_module  # noqa: E402  (DATABASE_URL must be set first)
    import ask
    import config
    import embeddings
    import indexing
    import llm
    from eval.pool import labelled_chunk_ids
    from models import Candidate, Job, ResumeChunk

    if not config.get_api_key():
        raise SystemExit("no Gemini API key configured")

    # Record Gemini exceptions (the route swallows them into llm_error) without changing behaviour.
    errors: list[str] = []
    real_generate = llm.generate_text

    def recording_generate(prompt: str, key: str) -> str:
        try:
            return real_generate(prompt, key)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {str(exc)[:200]}")
            raise
    llm.generate_text = recording_generate

    provider = embeddings.get_provider()
    session = app_module.SessionLocal()
    job = Job(title="Benchmark pool", description_text="(benchmark)")
    session.add(job)
    for path in corpus_files():
        session.add(Candidate(name=resume_key(path), job=job, resume_filename=resume_key(path),
                              resume_text=path.read_text(encoding="utf-8")))
    session.flush()
    for candidate in session.query(Candidate).order_by(Candidate.id):
        indexing.index_candidate(session, candidate, provider)
    session.commit()
    n_candidates = session.query(Candidate).count()

    benchmark = load()
    questions = [dict(q, kind="positive") for q in benchmark["questions"]]
    questions += [dict(q, kind="negative", relevant=[]) for q in benchmark["negative_questions"]]
    client = app_module.app.test_client()
    rows = []
    last = 0.0
    for q in questions:
        labelled = {(c.candidate_id, c.char_start, c.char_end) for c in session.query(ResumeChunk)
                    .filter(ResumeChunk.id.in_(labelled_chunk_ids(session, q)))}
        wait = PACING_SECONDS - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
        errors.clear()
        resp = client.post("/api/ask", json={"question": q["question"]})
        last = time.monotonic()
        body = resp.get_json() or {}
        cits = [{"number": c["number"], "candidate": c["candidate_name"], "section": c["section"],
                 "char_start": c["char_start"], "char_end": c["char_end"], "similarity": c["similarity"],
                 "labelled": (c["candidate_id"], c["char_start"], c["char_end"]) in labelled,
                 "text": c["text"]} for c in body.get("citations", [])]
        rows.append({
            "id": q["id"], "kind": q["kind"], "question": q["question"], "http_status": resp.status_code,
            "answer": body.get("answer"), "found": body.get("found"), "generated": body.get("generated"),
            "summary_unavailable": body.get("summary_unavailable"),
            "summary_unavailable_reason": body.get("summary_unavailable_reason"),
            "top_similarity": body.get("top_similarity"), "citations": cits,
            "labelled_resumes": sorted({lab["resume"] for lab in q["relevant"]}),
            "llm_errors": list(errors), "error": body.get("error"),
        })
        print(f"{q['id']}: status={resp.status_code} found={body.get('found')} generated={body.get('generated')} "
              f"reason={body.get('summary_unavailable_reason')} errors={len(errors)}", flush=True)
    session.close()

    return {
        "model": config.GEMINI_MODEL,
        "date": datetime.date.today().isoformat(),
        "commit": subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip(),
        "route": "POST /api/ask (Flask test client, throwaway SQLite)",
        "candidates_indexed": n_candidates, "pacing_seconds": PACING_SECONDS,
        "threshold": ask.NOT_FOUND_THRESHOLD, "results": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", help="read GOOGLE_API_KEY from this .env into the process only")
    args = parser.parse_args(argv)
    result = run(args.env_file)
    RESULTS_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
