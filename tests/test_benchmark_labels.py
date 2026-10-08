"""The retrieval benchmark's labels stay valid as resumes, chunking or labels change."""
from eval import benchmark


def test_every_label_matches_exactly_one_chunk():
    data = benchmark.load()
    assert benchmark.validate(data, benchmark.chunks_by_resume()) == []
    assert len(data["questions"]) >= 30


def test_questions_have_rationales_and_unique_ids():
    data = benchmark.load()
    ids = [q["id"] for q in data["questions"]] + [n["id"] for n in data["negative_questions"]]
    assert len(ids) == len(set(ids))
    assert all(q["rationale"].strip() and q["relevant"] for q in data["questions"])
