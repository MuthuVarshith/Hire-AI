"""Chunk and embed resumes and job descriptions for retrieval.

Each document is re-chunked from scratch on every (re)index, so stored chunks
always reflect the current text and the current embedding provider. If the
provider is unavailable, chunks are still stored without vectors and
`python -m indexing --reindex` fills them in later.

Usage:
    python -m indexing --reindex            # every candidate and job, current provider
"""
import argparse
import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

import embeddings
from chunking import Chunk, chunk_job_description, chunk_resume
from embeddings import EmbeddingProvider, EmbeddingUnavailable
from models import Candidate, Job, JobChunk, ResumeChunk

logger = logging.getLogger(__name__)

_UNSET: object = object()


@dataclass(frozen=True)
class IndexResult:
    chunks: int
    embedded: bool
    model: str | None


def _resolve(provider: EmbeddingProvider | None | object) -> EmbeddingProvider | None:
    """The given provider, or the configured one; None if it can't be loaded."""
    if provider is not _UNSET:
        return provider  # type: ignore[return-value]
    try:
        return embeddings.get_provider()
    except EmbeddingUnavailable as exc:
        logger.warning("Embedding provider unavailable, storing chunks without vectors: %s", exc)
        return None


def _fits(provider: EmbeddingProvider | None) -> Callable[[Chunk], bool] | None:
    """Chunk check for the chunker: measures exactly the string that will be embedded."""
    if provider is None:
        return None
    return lambda chunk: provider.fits(chunk.embedding_text)


def _vectors(provider: EmbeddingProvider | None, chunks: list[Chunk]) -> list[list[float]] | None:
    if provider is None or not chunks:
        return None
    try:
        return provider.embed([c.embedding_text for c in chunks], kind="document")
    except EmbeddingUnavailable as exc:
        logger.warning("Embedding failed, storing chunks without vectors: %s", exc)
        return None


def index_candidate(session: Session, candidate: Candidate,
                    provider: EmbeddingProvider | None | object = _UNSET) -> IndexResult:
    """Replace the candidate's chunks. The caller commits."""
    active = _resolve(provider)
    chunks = chunk_resume(candidate.resume_text or "", fits=_fits(active))
    vectors = _vectors(active, chunks)
    candidate.chunks.clear()
    session.flush()  # delete old rows before inserting, so (candidate_id, chunk_index) stays unique
    for i, chunk in enumerate(chunks):
        candidate.chunks.append(ResumeChunk(
            chunk_index=chunk.index, section=chunk.section, heading=chunk.heading, text=chunk.text,
            char_start=chunk.start, char_end=chunk.end, source_file=candidate.resume_filename,
            embedding=vectors[i] if vectors else None,
            embedding_model=active.name if vectors and active else None,
        ))
    return IndexResult(len(chunks), vectors is not None, active.name if vectors and active else None)


def index_job(session: Session, job: Job, provider: EmbeddingProvider | None | object = _UNSET) -> IndexResult:
    """Replace the job description's chunks. The caller commits."""
    active = _resolve(provider)
    chunks = chunk_job_description(job.description_text or "", fits=_fits(active))
    vectors = _vectors(active, chunks)
    job.chunks.clear()
    session.flush()
    for i, chunk in enumerate(chunks):
        job.chunks.append(JobChunk(
            chunk_index=chunk.index, section=chunk.section, heading=chunk.heading, text=chunk.text,
            char_start=chunk.start, char_end=chunk.end,
            embedding=vectors[i] if vectors else None,
            embedding_model=active.name if vectors and active else None,
        ))
    return IndexResult(len(chunks), vectors is not None, active.name if vectors and active else None)


def reindex_all(session: Session, provider: EmbeddingProvider | None | object = _UNSET) -> dict[str, int]:
    """Re-chunk and re-embed every candidate and job; commits once at the end."""
    active = _resolve(provider)
    totals = {"candidates": 0, "jobs": 0, "chunks": 0, "without_vectors": 0}
    for candidate in session.query(Candidate).order_by(Candidate.id):
        result = index_candidate(session, candidate, active)
        totals["candidates"] += 1
        totals["chunks"] += result.chunks
        totals["without_vectors"] += 0 if result.embedded else result.chunks
    for job in session.query(Job).order_by(Job.id):
        result = index_job(session, job, active)
        totals["jobs"] += 1
        totals["chunks"] += result.chunks
        totals["without_vectors"] += 0 if result.embedded else result.chunks
    session.commit()
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reindex", action="store_true", help="re-chunk and re-embed every candidate and job")
    args = parser.parse_args(argv)
    if not args.reindex:
        parser.print_help()
        return 2

    import os

    from sqlalchemy.orm import sessionmaker

    from database import create_database_engine

    engine = create_database_engine(os.getenv("DATABASE_URL", "sqlite:///recruiting_agent.db"))
    with sessionmaker(bind=engine)() as session:
        totals = reindex_all(session)
    print(f"Reindexed {totals['candidates']} candidates and {totals['jobs']} jobs: {totals['chunks']} chunks, "
          f"{totals['without_vectors']} without vectors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
