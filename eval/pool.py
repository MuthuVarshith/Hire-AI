"""Index the benchmark corpus into a throwaway SQLite database, exactly as eval/measure.py does.

Same Job/Candidate rows (name and filename are the resume key), same indexing.index_candidate call, and
the same label resolution against stored chunks. SQLite means exact (brute-force) vector search.
"""
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from eval.benchmark import corpus_files, resume_key, squash


@contextmanager
def indexed_pool(provider: Any) -> Iterator[Session]:
    import indexing
    from database import create_database_engine
    from models import Candidate, Job

    with tempfile.TemporaryDirectory() as tmp:
        engine = create_database_engine(f"sqlite:///{(Path(tmp) / 'pool.db').as_posix()}")
        try:
            with Session(engine) as session:
                job = Job(title="Benchmark pool", description_text="(benchmark)")
                session.add(job)
                for path in corpus_files():
                    session.add(Candidate(name=resume_key(path), job=job, resume_filename=resume_key(path),
                                          resume_text=path.read_text(encoding="utf-8")))
                session.flush()
                for candidate in session.query(Candidate).order_by(Candidate.id):
                    indexing.index_candidate(session, candidate, provider)
                session.commit()
                yield session
        finally:
            engine.dispose()


def labelled_chunk_ids(session: Session, question: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Map stored chunk id -> label for each label of a question (each must match exactly one chunk)."""
    from models import Candidate, ResumeChunk

    rows = session.query(ResumeChunk, Candidate.resume_filename).join(Candidate).all()
    out = {}
    for label in question["relevant"]:
        found = [c for c, resume in rows if resume == label["resume"] and c.section == label["section"]
                 and squash(label["contains"]) in squash(c.text)]
        if len(found) != 1:
            raise SystemExit(f"{question['id']}: label {label} matched {len(found)} stored chunks")
        out[found[0].id] = label
    return out
