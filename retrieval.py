"""Search over resume chunks: vector, BM25, hybrid (reciprocal rank fusion) and reranking.

Every method returns the same `Hit` records, pointing at exact chunk offsets in the
candidate's resume, so answers can cite the passage they used. Retrieval never reads
or writes candidate scores.

Vector search uses pgvector on PostgreSQL (an HNSW index for the default model) and
brute-force cosine similarity on SQLite.
"""
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any

from rank_bm25 import BM25Okapi
from sqlalchemy import text as sql
from sqlalchemy.orm import Session

from chunking import SECTION_LABELS
from embeddings import EmbeddingProvider
from models import Candidate, ResumeChunk

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DIMENSION = 384  # the partial HNSW index in migration 0003 covers this model and dimension
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#]*(?:\.[a-z0-9]+)*")


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    candidate_id: int
    section: str
    text: str
    char_start: int
    char_end: int
    score: float
    method: str


@dataclass(frozen=True)
class RetrievalConfig:
    use_vector: bool = True
    use_bm25: bool = True
    use_reranker: bool = False
    k: int = 10                    # hits returned
    pool: int = 50                 # hits each method contributes before fusion / reranking
    rrf_k: int = 60                # standard RRF constant (Cormack et al., 2009)


def tokenize(value: str) -> list[str]:
    """Lowercase word tokens that keep tech names intact: c++, c#, node.js, gpt-4 -> gpt, 4."""
    return _TOKEN.findall(value.lower())


def labelled(section: str, value: str) -> str:
    """The text both methods see; matches what the indexer embeds (chunking.Chunk.embedding_text)."""
    return f"{SECTION_LABELS.get(section, section.title())}: {value}"


def _hit(row: Any, score: float, method: str) -> Hit:
    return Hit(row.id, row.candidate_id, row.section, row.text, row.char_start, row.char_end, float(score), method)


class Retriever:
    def __init__(self, session: Session, provider: EmbeddingProvider | None = None,
                 reranker: Any = None) -> None:
        self.session = session
        self.provider = provider
        self._reranker = reranker

    # --- candidate chunks -----------------------------------------------------------
    def _chunks(self, job_id: int | None, model: str | None = None) -> list[ResumeChunk]:
        query = self.session.query(ResumeChunk)
        if job_id is not None:
            query = query.join(Candidate).filter(Candidate.job_id == job_id)
        if model is not None:
            query = query.filter(ResumeChunk.embedding_model == model)
        return query.order_by(ResumeChunk.id).all()

    # --- vector ---------------------------------------------------------------------
    def vector_search(self, query: str, limit: int = 10, job_id: int | None = None) -> list[Hit]:
        if self.provider is None:
            return []
        vector = self.provider.embed([query], kind="query")[0]
        if self.session.get_bind().dialect.name == "postgresql":
            return self._vector_postgres(vector, limit, job_id)
        return self._vector_brute_force(vector, limit, job_id)

    def _vector_brute_force(self, vector: Sequence[float], limit: int, job_id: int | None) -> list[Hit]:
        assert self.provider is not None
        scored = []
        for chunk in self._chunks(job_id, self.provider.name):
            stored = chunk.embedding or []
            if len(stored) == len(vector):
                scored.append((sum(a * b for a, b in zip(stored, vector, strict=True)), chunk))  # unit vectors
        scored.sort(key=lambda pair: (-pair[0], pair[1].id))
        return [_hit(chunk, score, "vector") for score, chunk in scored[:limit]]

    def _vector_postgres(self, vector: Sequence[float], limit: int, job_id: int | None) -> list[Hit]:
        assert self.provider is not None
        dim = int(self.provider.dimension)
        # The same cast expression as the partial HNSW index, so the planner can use it.
        distance = f"(rc.embedding::vector({dim})) <=> CAST(:q AS vector({dim}))"
        job_filter = "AND c.job_id = :job_id" if job_id is not None else ""
        if job_id is not None:
            # HNSW filters after the graph search; iterative scan keeps searching until `limit` rows match.
            self.session.execute(sql("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        rows = self.session.execute(sql(f"""
            SELECT rc.id, rc.candidate_id, rc.section, rc.text, rc.char_start, rc.char_end,
                   1 - ({distance}) AS similarity
            FROM resume_chunks rc JOIN candidates c ON c.id = rc.candidate_id
            WHERE rc.embedding_model = :model {job_filter}
            ORDER BY {distance}, rc.id
            LIMIT :limit"""), {"q": str([float(x) for x in vector]), "model": self.provider.name,
                               "limit": limit, "job_id": job_id}).all()
        return [_hit(row, row.similarity, "vector") for row in rows]

    # --- BM25 -----------------------------------------------------------------------
    def bm25_search(self, query: str, limit: int = 10, job_id: int | None = None) -> list[Hit]:
        chunks = self._chunks(job_id)
        terms = tokenize(query)
        if not chunks or not terms:
            return []
        index = BM25Okapi([tokenize(labelled(c.section, c.text)) or ["_"] for c in chunks])
        scores = index.get_scores(terms)
        ranked = sorted(zip(scores, chunks, strict=True), key=lambda pair: (-pair[0], pair[1].id))
        return [_hit(chunk, score, "bm25") for score, chunk in ranked[:limit] if score > 0]

    # --- fusion and reranking -------------------------------------------------------------
    @staticmethod
    def fuse(rankings: Sequence[Sequence[Hit]], rrf_k: int = 60) -> list[Hit]:
        """Reciprocal rank fusion: sum of 1 / (rrf_k + rank) over the lists a chunk appears in."""
        totals: dict[int, float] = {}
        first: dict[int, Hit] = {}
        for ranking in rankings:
            for rank, hit in enumerate(ranking, start=1):
                totals[hit.chunk_id] = totals.get(hit.chunk_id, 0.0) + 1.0 / (rrf_k + rank)
                first.setdefault(hit.chunk_id, hit)
        ordered = sorted(totals, key=lambda cid: (-totals[cid], cid))
        return [replace(first[cid], score=totals[cid], method="rrf") for cid in ordered]

    def reranker(self) -> Any:
        if self._reranker is None:
            self._reranker = _load_cross_encoder()
        return self._reranker

    def rerank(self, query: str, hits: Sequence[Hit]) -> list[Hit]:
        if not hits:
            return []
        scores = self.reranker().predict([(query, labelled(h.section, h.text)) for h in hits],
                                         show_progress_bar=False)
        rescored = [replace(h, score=float(s), method="rerank") for h, s in zip(hits, scores, strict=True)]
        return sorted(rescored, key=lambda h: (-h.score, h.chunk_id))

    def search(self, query: str, config: RetrievalConfig | None = None,
               job_id: int | None = None) -> list[Hit]:
        config = config or RetrievalConfig()
        rankings = []
        if config.use_vector:
            rankings.append(self.vector_search(query, config.pool, job_id))
        if config.use_bm25:
            rankings.append(self.bm25_search(query, config.pool, job_id))
        if not rankings:
            raise ValueError("enable at least one of vector and BM25 search")
        hits = rankings[0] if len(rankings) == 1 else self.fuse(rankings, config.rrf_k)
        if config.use_reranker:
            hits = self.rerank(query, hits[:config.pool])
        return list(hits[:config.k])


@lru_cache(maxsize=1)
def _load_cross_encoder() -> Any:
    from sentence_transformers import CrossEncoder

    return CrossEncoder(RERANKER_MODEL)


def sigmoid(value: float) -> float:
    """Maps a cross-encoder logit to (0, 1), for confidence thresholds."""
    return 1.0 / (1.0 + math.exp(-value))
