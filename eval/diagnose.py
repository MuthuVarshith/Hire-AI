"""Print the vector-search rank and similarity of every labelled chunk for one benchmark question.

    python -m eval.diagnose q16 [--top 10]

Indexes the benchmark corpus into a temporary SQLite database (exact search) the same way as
eval/measure.py. Diagnostic only: it changes no retrieval parameter, chunking, or prompt.
"""
import argparse

from eval.benchmark import load, squash
from eval.pool import indexed_pool, labelled_chunk_ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question_id")
    parser.add_argument("--top", type=int, default=10, help="also print the top N chunks")
    args = parser.parse_args(argv)
    question = next((q for q in load()["questions"] if q["id"] == args.question_id), None)
    if question is None:
        raise SystemExit(f"unknown question id {args.question_id}")

    from embeddings import SentenceTransformerProvider
    from models import Candidate
    from retrieval import Retriever

    provider = SentenceTransformerProvider()
    with indexed_pool(provider) as session:
        labels = labelled_chunk_ids(session, question)
        names: dict[int, str] = {cid: str(fn) for cid, fn in session.query(Candidate.id, Candidate.resume_filename)}
        hits = Retriever(session, provider).vector_search(question["question"], 10_000, None)
        print(f"{question['id']}: {question['question']}  ({len(hits)} chunks ranked)\n")
        print("Labelled chunks:")
        for rank, hit in enumerate(hits, start=1):
            if hit.chunk_id in labels:
                print(f"  rank {rank:3d}  sim {hit.score:.4f}  {names[hit.candidate_id]} [{hit.section}]  "
                      f"{squash(hit.text)[:90]}")
        print(f"\nTop {args.top}:")
        for rank, hit in enumerate(hits[:args.top], start=1):
            mark = "*" if hit.chunk_id in labels else " "
            print(f" {mark}rank {rank:3d}  sim {hit.score:.4f}  {names[hit.candidate_id]} [{hit.section}]  "
                  f"{squash(hit.text)[:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
