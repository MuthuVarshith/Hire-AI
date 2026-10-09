"""Top-1 retrieval similarity for the benchmark questions and the negatives (no LLM, no network calls).

    python -m eval.ask_similarity

Indexes the synthetic benchmark resumes into a temporary SQLite database (eval.pool), runs the
retrieval configuration ask.py uses, and prints the top-1 cosine similarity per question. These are
the numbers behind ask.NOT_FOUND_THRESHOLD (eval/ask_calibration.md).
"""
import statistics

from eval.benchmark import load


def main() -> int:
    import ask
    from embeddings import SentenceTransformerProvider
    from eval.pool import indexed_pool
    from retrieval import Retriever

    benchmark = load()
    provider = SentenceTransformerProvider()
    scores: dict[str, dict[str, float]] = {"positive": {}, "negative": {}}
    with indexed_pool(provider) as session:
        retriever = Retriever(session, provider)
        for kind, key in (("positive", "questions"), ("negative", "negative_questions")):
            for q in benchmark[key]:
                hits = retriever.search(q["question"], ask.CHOSEN_CONFIG)
                scores[kind][q["id"]] = hits[0].score if hits else float("nan")
    for kind in ("negative", "positive"):
        for qid, score in scores[kind].items():
            print(f"{kind:8} {qid}: {score:.3f}")
    pos = scores["positive"]
    lo, hi = min(pos, key=pos.__getitem__), max(pos, key=pos.__getitem__)
    print(f"answerable n={len(pos)} min {pos[lo]:.3f} ({lo}) median {statistics.median(pos.values()):.3f} "
          f"max {pos[hi]:.3f} ({hi})")
    worst_neg = max(scores["negative"].values())
    print(f"answerable below the highest negative ({worst_neg:.3f}): {sum(s < worst_neg for s in pos.values())}")
    print(f"refused at {ask.NOT_FOUND_THRESHOLD}: answerable "
          f"{sum(s < ask.NOT_FOUND_THRESHOLD for s in pos.values())}, negatives "
          f"{sum(s < ask.NOT_FOUND_THRESHOLD for s in scores['negative'].values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
