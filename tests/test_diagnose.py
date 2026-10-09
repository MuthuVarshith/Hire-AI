"""The retrieval diagnostic's report formatting (no models or database needed)."""
from retrieval import Hit

from eval.diagnose import ranks, report


def _hit(chunk_id: int, score: float, method: str) -> Hit:
    return Hit(chunk_id, chunk_id * 10, "skills", f"text {chunk_id}", 0, 6, score, method)


def test_report_shows_each_labelled_chunk_under_every_method():
    vector = [_hit(1, 0.9, "vector"), _hit(2, 0.5, "vector"), _hit(3, 0.1, "vector")]
    bm25 = [_hit(3, 4.0, "bm25")]  # chunk 2 has no BM25 score
    labels = {2: {"resume": "r2.txt", "section": "skills"}, 3: {"resume": "r3.txt", "section": "skills"}}
    names = {10: "r1.txt", 20: "r2.txt", 30: "r3.txt"}
    lines = report({"id": "q", "question": "?"}, labels, names, {"vector": vector, "bm25": bm25}, top=2)
    row2 = next(line for line in lines if line.startswith("  r2.txt"))
    assert "vector: rank   2" in row2 and "bm25: rank   -" in row2
    row3 = next(line for line in lines if line.startswith("  r3.txt"))
    assert "vector: rank   3" in row3 and "bm25: rank   1" in row3
    assert " *rank   2  score  0.5000  r2.txt" in "\n".join(lines)
    assert ranks(vector)[3] == (3, 0.1)
