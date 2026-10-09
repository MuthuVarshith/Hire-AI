"""Print the vector and BM25 rank and score of every labelled chunk for one benchmark question.

    python -m eval.diagnose q16 [--top 10]

Indexes the benchmark corpus into a temporary SQLite database (exact search) the same way as
eval/measure.py, via eval/pool.py. Diagnostic only: it changes no retrieval parameter, chunking, or prompt.
"""
import argparse
from typing import Any

from eval.benchmark import load, squash


def ranks(hits: list[Any]) -> dict[int, tuple[int, float]]:
    """chunk id -> (1-based rank, score) for a full ranking."""
    return {hit.chunk_id: (rank, hit.score) for rank, hit in enumerate(hits, start=1)}


def describe(rank_score: tuple[int, float] | None) -> str:
    if rank_score is None:
        return "rank   -  score     -  "
    return f"rank {rank_score[0]:3d}  score {rank_score[1]:7.4f}"


def report(question: dict[str, Any], labels: dict[int, Any], names: dict[int, str],
           methods: dict[str, list[Any]], top: int) -> list[str]:
    """The diagnostic lines for one question, given each method's full ranking."""
    tables = {method: ranks(hits) for method, hits in methods.items()}
    texts = {hit.chunk_id: hit for hits in methods.values() for hit in hits}
    lines = [f"{question['id']}: {question['question']}", "", "Labelled chunks:"]
    for chunk_id, label in labels.items():
        cells = "  ".join(f"{m}: {describe(tables[m].get(chunk_id))}" for m in methods)
        lines.append(f"  {label['resume']} [{label['section']}]  {cells}")
        hit = texts.get(chunk_id)
        if hit is not None:
            lines.append(f"      {squash(hit.text)[:110]}")
    for method, hits in methods.items():
        lines += ["", f"Top {top} by {method} (* = labelled):"]
        for rank, hit in enumerate(hits[:top], start=1):
            mark = "*" if hit.chunk_id in labels else " "
            lines.append(f" {mark}rank {rank:3d}  score {hit.score:7.4f}  {names[hit.candidate_id]} "
                         f"[{hit.section}]  {squash(hit.text)[:80]}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("question_id")
    parser.add_argument("--top", type=int, default=10, help="also print each method's top N chunks")
    args = parser.parse_args(argv)
    question = next((q for q in load()["questions"] if q["id"] == args.question_id), None)
    if question is None:
        raise SystemExit(f"unknown question id {args.question_id}")

    from embeddings import SentenceTransformerProvider
    from eval.pool import indexed_pool, labelled_chunk_ids
    from models import Candidate
    from retrieval import Retriever

    provider = SentenceTransformerProvider()
    with indexed_pool(provider) as session:
        labels = labelled_chunk_ids(session, question)
        names = {int(cid): str(fn) for cid, fn in session.query(Candidate.id, Candidate.resume_filename)}
        retriever = Retriever(session, provider)
        methods = {"vector": retriever.vector_search(question["question"], 10_000, None),
                   "bm25": retriever.bm25_search(question["question"], 10_000, None)}
        print("\n".join(report(question, labels, names, methods, args.top)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
