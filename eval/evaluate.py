"""Answer-evaluation metrics that need no LLM (eval/answer_eval_protocol.md, sections 3 and 4.1-4.3).

    python -m eval.evaluate

- Context recall and precision of the retrieval /api/ask uses (ask.CHOSEN_CONFIG, k = 8), against
  the labels, for the 30 benchmark questions and the 20 held-out answerable questions.
- Citation validity of the live answers (eval/ask_live_batch*.json): the share of each answer's
  citations that are labelled chunks.
- Not-found behaviour of the current cutoff on the held-out set, from top-1 similarity alone.
- The outcome of each benchmark question's live row.

Writes eval/results/evaluate.json. Retrieval runs on a throwaway SQLite database (eval/pool.py)
with local embeddings; nothing is sent to any service.
"""
import argparse
import datetime
import importlib.metadata as md
import json
import os
import subprocess
from collections.abc import Sequence
from statistics import mean
from typing import Any

from eval.answers import ANSWERED, OUTCOMES, LiveAnswer, live_files, select_answers
from eval.benchmark import ROOT
from eval.benchmark import load as load_benchmark
from eval.golden import load_heldout

RESULTS_DIR = ROOT / "eval" / "results"
EVALUATE_JSON = RESULTS_DIR / "evaluate.json"


# --- metric formulas (protocol section 4.1) --------------------------------------------------
def context_recall(retrieved: Sequence[int], labelled: set[int]) -> float:
    """RAGAS IDBasedContextRecall: labelled chunks retrieved / labelled chunks."""
    return len(set(retrieved) & labelled) / len(labelled) if labelled else float("nan")


def id_context_precision(retrieved: Sequence[int], labelled: set[int]) -> float:
    """RAGAS IDBasedContextPrecision: retrieved chunks that are labelled / retrieved chunks."""
    unique = set(retrieved)
    return len(unique & labelled) / len(unique) if unique else float("nan")


def rank_context_precision(retrieved: Sequence[int], labelled: set[int]) -> float:
    """RAGAS context precision (average precision over the ranks), with labels as the relevance verdicts:
    sum over k of precision@k * v_k, divided by the number of relevant chunks retrieved; 0 if none."""
    verdicts = [1 if chunk in labelled else 0 for chunk in retrieved]
    hits = sum(verdicts)
    if not hits:
        return 0.0
    return sum(sum(verdicts[:k + 1]) / (k + 1) * v for k, v in enumerate(verdicts)) / hits


def ragas_id_scores(pairs: list[tuple[list[int], set[int]]]) -> tuple[str, list[tuple[float, float]]] | None:
    """(ragas version, [(ID-based precision, recall)]) computed by RAGAS itself, or None without ragas."""
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"  # ragas otherwise sends usage analytics
    try:
        from ragas.dataset_schema import SingleTurnSample
        from ragas.metrics._context_precision import IDBasedContextPrecision
        from ragas.metrics._context_recall import IDBasedContextRecall
    except ImportError:
        return None
    precision, recall = IDBasedContextPrecision(), IDBasedContextRecall()
    scores = []
    for retrieved, labelled in pairs:
        sample = SingleTurnSample(retrieved_context_ids=[str(c) for c in retrieved],
                                  reference_context_ids=[str(c) for c in sorted(labelled)])
        scores.append((float(precision.single_turn_score(sample)), float(recall.single_turn_score(sample))))
    return md.version("ragas"), scores


# --- retrieval ---------------------------------------------------------------------------
def retrieve(questions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Run the /api/ask retrieval for each question: ranked chunk ids, labelled chunk ids, top-1 similarity.
    A question without "relevant" labels (an unanswerable one) gets an empty label set."""
    import ask
    from embeddings import SentenceTransformerProvider
    from eval.pool import indexed_pool, labelled_chunk_ids
    from retrieval import Retriever

    provider = SentenceTransformerProvider()
    out: dict[str, dict[str, Any]] = {}
    with indexed_pool(provider) as session:
        retriever = Retriever(session, provider)
        for q in questions:
            hits = retriever.search(q["question"], ask.CHOSEN_CONFIG)
            labels = labelled_chunk_ids(session, {"id": q["id"], "relevant": q.get("relevant", [])})
            out[q["id"]] = {"retrieved": [h.chunk_id for h in hits], "labelled": sorted(labels),
                            "top1": hits[0].score if hits else None}
    return out


def context_block(questions: list[dict[str, Any]], runs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for q in questions:
        run = runs[q["id"]]
        retrieved, labelled = run["retrieved"], set(run["labelled"])
        rows.append({"id": q["id"], "retrieved": len(retrieved), "labelled": len(labelled),
                     "labelled_retrieved": len(set(retrieved) & labelled),
                     "context_recall": context_recall(retrieved, labelled),
                     "context_precision_id": id_context_precision(retrieved, labelled),
                     "context_precision_rank": rank_context_precision(retrieved, labelled)})
    return {"n": len(rows),
            "context_recall": mean(r["context_recall"] for r in rows),
            "context_precision_id": mean(r["context_precision_id"] for r in rows),
            "context_precision_rank": mean(r["context_precision_rank"] for r in rows),
            "per_question": rows}


def refusals(top1: dict[str, float | None], cutoff: float) -> dict[str, Any]:
    """Questions refused by the similarity floor (top-1 below the cutoff, or nothing retrieved)."""
    refused = sorted(qid for qid, score in top1.items() if score is None or score < cutoff)
    return {"n": len(top1), "refused": len(refused), "refused_ids": refused, "top1": top1}


# --- live answers ------------------------------------------------------------------------
def citation_validity(answers: list[LiveAnswer]) -> dict[str, Any]:
    """Share of each answered row's citations that are labelled chunks (ask_live's `labelled` flag)."""
    rows = []
    for a in answers:
        if a.outcome != ANSWERED or a.row is None:
            continue
        cites = a.row.get("citations", [])
        labelled = sum(1 for c in cites if c.get("labelled") is True)
        rows.append({"id": a.question_id, "kind": a.kind, "citations": len(cites), "labelled": labelled,
                     "validity": labelled / len(cites) if cites else None})
    total = sum(r["citations"] for r in rows)
    scored = [r["validity"] for r in rows if r["validity"] is not None]
    return {"answers": len(rows), "citations": total, "labelled": sum(r["labelled"] for r in rows),
            "micro": sum(r["labelled"] for r in rows) / total if total else None,
            "macro": mean(scored) if scored else None, "per_answer": rows}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def provenance(answers: list[LiveAnswer]) -> list[dict[str, Any]]:
    """Each batch file's commit, and the /api/ask files that differ from the first batch's commit."""
    from eval.ask_live import ASK_PATH

    files = []
    for path in live_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        name = path.relative_to(ROOT).as_posix()
        files.append({"file": name, "commit": data.get("commit"), "model": data.get("model"),
                      "date": data.get("date"), "rows_used": sorted(a.question_id for a in answers if a.file == name)})
    first = next((f["commit"] for f in files if f["commit"]), None)
    for f in files:
        changed = (_git("diff", "--name-only", first, f["commit"], "--", *ASK_PATH).splitlines()
                   if first and f["commit"] and f["commit"] != first else [])
        f["ask_files_changed_since_first_batch"] = changed
    return files


def answers_block(answers: list[LiveAnswer]) -> dict[str, Any]:
    counts = {kind: {name: sum(1 for a in answers if a.kind == kind and a.outcome == name) for name in OUTCOMES}
              for kind in ("positive", "negative")}
    return {"rule": "first generated row in batch order; a similarity-floor refusal is final (protocol section 2)",
            "outcome_counts": counts,
            "rows": [{"id": a.question_id, "kind": a.kind, "outcome": a.outcome, "file": a.file,
                      "commit": a.commit} for a in answers]}


# --- run ---------------------------------------------------------------------------------
def run() -> dict[str, Any]:
    import ask

    benchmark, heldout = load_benchmark(), load_heldout()
    bench_q = benchmark["questions"]
    held_a, held_u = heldout["answerable"], heldout["unanswerable"]
    runs = retrieve(bench_q + held_a + held_u)

    pairs = [(runs[q["id"]]["retrieved"], set(runs[q["id"]]["labelled"])) for q in bench_q + held_a]
    ours = [(id_context_precision(r, labelled), context_recall(r, labelled)) for r, labelled in pairs]
    theirs = ragas_id_scores(pairs)
    ragas_check: dict[str, Any] = {"ragas_version": None}
    if theirs is not None:
        version, scores = theirs
        ragas_check = {"ragas_version": version,
                       "id_based_precision_agrees": all(abs(a[0] - b[0]) < 1e-9 for a, b in zip(ours, scores)),
                       "id_based_recall_agrees": all(abs(a[1] - b[1]) < 1e-9 for a, b in zip(ours, scores))}

    answers = select_answers()
    cutoff = ask.NOT_FOUND_THRESHOLD
    return {
        "generated_by": "python -m eval.evaluate",
        "protocol": "eval/answer_eval_protocol.md",
        "commit": _git("rev-parse", "--short", "HEAD"),
        "uncommitted_changes": bool(_git("status", "--porcelain")),
        "date": datetime.date.today().isoformat(),
        "retrieval": {"config": "ask.CHOSEN_CONFIG: vector search, k = 8", "database": "SQLite, exact search",
                      "embedding_model": "sentence-transformers/all-MiniLM-L6-v2 (local)",
                      "sentence_transformers": md.version("sentence-transformers")},
        "context": {"benchmark": context_block(bench_q, runs), "heldout_answerable": context_block(held_a, runs)},
        "ragas_check": ragas_check,
        "not_found_similarity": {
            "cutoff": cutoff,
            "heldout_answerable": refusals({q["id"]: runs[q["id"]]["top1"] for q in held_a}, cutoff),
            "heldout_unanswerable": refusals({q["id"]: runs[q["id"]]["top1"] for q in held_u}, cutoff),
        },
        "answers": answers_block(answers),
        "answer_files": provenance(answers),
        "citation_validity": citation_validity(answers),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.parse_args(argv)
    result = run()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    EVALUATE_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {EVALUATE_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
