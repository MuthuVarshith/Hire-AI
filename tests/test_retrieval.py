"""Retrieval: vector, BM25, reciprocal rank fusion, reranking, job filters, and the HNSW index."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

import embeddings
import indexing
from database import create_database_engine
from models import Candidate, Job
from retrieval import Hit, RetrievalConfig, Retriever, tokenize
from retrieval_langchain import CandidatePoolRetriever

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

RESUMES = {
    "Ada": ("Ada Lin\n\nSkills\nPython, FastAPI, Docker, PostgreSQL\n\n"
            "Experience\nShipped FastAPI services to production."),
    "Bo": "Bo Ray\n\nSkills\nReact, TypeScript, CSS\n\nExperience\nBuilt accessible React dashboards.",
    "Cy": "Cy Moss\n\nSkills\nKubernetes, Terraform, AWS\n\nExperience\nRan EKS clusters with Terraform.",
}


class KeywordProvider:
    """A tiny deterministic 'embedding': one dimension per keyword group, unit-normalized."""

    name = "keyword/4"
    dimension = 4
    GROUPS = (("python", "fastapi", "django"), ("react", "typescript", "css"),
              ("kubernetes", "terraform", "eks", "aws"), ("docker",))

    def embed(self, texts, kind="document"):
        out = []
        for t in texts:
            words = set(tokenize(t))
            out.append(embeddings.normalize([float(len(words & set(g))) or 0.01 for g in self.GROUPS]))
        return out

    def fits(self, value):
        return True


class ReverseReranker:
    """Scores by text length, so its order is predictably different from the input order."""

    def predict(self, pairs, show_progress_bar=False):
        return [float(len(passage)) for _, passage in pairs]


def _populate(session, provider):
    jobs = {"backend": Job(title="Backend", description_text="x"), "other": Job(title="Other", description_text="y")}
    session.add_all(jobs.values())
    people = {}
    for name, resume in RESUMES.items():
        job = jobs["other"] if name == "Bo" else jobs["backend"]
        people[name] = Candidate(name=name, job=job, resume_text=resume)
        session.add(people[name])
    session.flush()
    for person in people.values():
        indexing.index_candidate(session, person, provider)
    session.commit()
    return jobs, people


@pytest.fixture(params=["sqlite", "postgresql"])
def session(request, tmp_path):
    if request.param == "sqlite":
        engine = create_database_engine(f"sqlite:///{(tmp_path / 'r.db').as_posix()}")
        with Session(engine) as s:
            yield s
        engine.dispose()
        return
    if not POSTGRES_URL:
        pytest.skip("TEST_POSTGRES_URL not set")
    name = f"hireai_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_database_engine(make_url(POSTGRES_URL).set(database=name).render_as_string(hide_password=False))
    try:
        with Session(engine) as s:
            yield s
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def _owners(session, hits):
    return [session.get(Candidate, h.candidate_id).name for h in hits]


def test_tokenize_keeps_tech_names():
    assert tokenize("C++, C#, Node.js and GPT-4 on k8s.") == ["c++", "c#", "node.js", "and", "gpt", "4", "on", "k8s"]


def test_vector_search_ranks_by_cosine(session):
    provider = KeywordProvider()
    _populate(session, provider)
    hits = Retriever(session, provider).vector_search("kubernetes and terraform", limit=3)
    assert _owners(session, hits)[0] == "Cy"
    assert all(isinstance(h, Hit) and h.method == "vector" for h in hits)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_vector_search_ignores_other_models(session):
    provider = KeywordProvider()
    _populate(session, provider)

    class OtherModel(KeywordProvider):
        name = "other/4"

    assert Retriever(session, OtherModel()).vector_search("python", limit=5) == []


def test_bm25_search_matches_keywords(session):
    _populate(session, KeywordProvider())
    hits = Retriever(session).bm25_search("react typescript", limit=5)
    assert _owners(session, hits)[0] == "Bo"
    assert Retriever(session).bm25_search("zzz unknownword", limit=5) == []


def test_hits_point_at_exact_resume_text(session):
    _populate(session, KeywordProvider())
    for hit in Retriever(session, KeywordProvider()).search("fastapi docker"):
        resume = session.get(Candidate, hit.candidate_id).resume_text
        assert resume[hit.char_start:hit.char_end] == hit.text


def test_job_filter(session):
    jobs, _ = _populate(session, KeywordProvider())
    retriever = Retriever(session, KeywordProvider())
    for method in (retriever.vector_search, retriever.bm25_search):
        assert set(_owners(session, method("react typescript python kubernetes", 10, jobs["backend"].id))) <= \
            {"Ada", "Cy"}


def test_reciprocal_rank_fusion_math():
    def hits(*ids):
        return [Hit(i, 0, "skills", "t", 0, 1, 0.0, "x") for i in ids]

    fused = Retriever.fuse([hits(1, 2, 3), hits(3, 1)], rrf_k=60)
    scores = {h.chunk_id: h.score for h in fused}
    assert scores[1] == pytest.approx(1 / 61 + 1 / 62)
    assert scores[3] == pytest.approx(1 / 63 + 1 / 61)
    assert scores[2] == pytest.approx(1 / 62)
    assert [h.chunk_id for h in fused] == [1, 3, 2] and all(h.method == "rrf" for h in fused)


def test_search_configurations(session):
    _populate(session, KeywordProvider())
    retriever = Retriever(session, KeywordProvider(), reranker=ReverseReranker())
    hybrid = retriever.search("fastapi docker", RetrievalConfig(k=3))
    assert {h.method for h in hybrid} == {"rrf"} and len(hybrid) == 3
    vector_only = retriever.search("fastapi docker", RetrievalConfig(use_bm25=False, k=3))
    assert {h.method for h in vector_only} == {"vector"}
    reranked = retriever.search("fastapi docker", RetrievalConfig(use_reranker=True, k=3))
    assert {h.method for h in reranked} == {"rerank"}
    assert [len(h.text) for h in reranked] == sorted((len(h.text) for h in reranked), reverse=True)
    with pytest.raises(ValueError):
        retriever.search("x", RetrievalConfig(use_vector=False, use_bm25=False))


def test_langchain_adapter_returns_documents_with_citations(session):
    _populate(session, KeywordProvider())
    docs = CandidatePoolRetriever(retriever=Retriever(session, KeywordProvider()),
                                  config=RetrievalConfig(k=2)).invoke("react typescript")
    assert len(docs) == 2
    assert {"chunk_id", "candidate_id", "section", "char_start", "char_end", "score", "method"} <= set(docs[0].metadata)


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL not set")
def test_postgres_uses_the_hnsw_index_for_the_default_model(session):
    if session.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL only")
    indexes = session.execute(text(
        "SELECT indexname FROM pg_indexes WHERE indexname LIKE '%hnsw%' ORDER BY indexname")).scalars().all()
    assert indexes == ["ix_job_chunks_embedding_hnsw_minilm", "ix_resume_chunks_embedding_hnsw_minilm"]

    session.execute(text("SET LOCAL enable_seqscan = off"))  # a tiny table would otherwise be seq-scanned
    plan = "\n".join(session.execute(text(
        "EXPLAIN SELECT id FROM resume_chunks WHERE embedding_model = 'sentence-transformers/all-MiniLM-L6-v2' "
        "ORDER BY (embedding::vector(384)) <=> CAST(:q AS vector(384)) LIMIT 5"),
        {"q": str([0.1] * 384)}).scalars().all())
    assert "ix_resume_chunks_embedding_hnsw_minilm" in plan
