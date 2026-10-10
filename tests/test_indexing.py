"""Resumes and job descriptions are chunked and embedded when saved, and kept in sync."""
import io
import logging
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

import embeddings
import indexing
import scorer
from embeddings import EmbeddingUnavailable
from models import Candidate, Job, JobChunk, ResumeChunk

REPO = Path(__file__).resolve().parent.parent
SAMPLE_JD = (REPO / "sample_jd" / "jd.txt").read_text(encoding="utf-8")
RESUME = REPO / "sample_resumes" / "resume_01_ananya_patel.txt"


class FakeProvider:
    """Deterministic 3-dimensional vectors; records every text it embeds."""

    name = "fake/3"
    dimension = 3

    def __init__(self, fail=None):
        self.fail, self.embedded = fail, []

    def embed(self, texts, kind="document"):
        if self.fail:
            raise self.fail
        self.embedded.extend(texts)
        return [embeddings.normalize([len(t), t.count(" ") + 1, 1.0]) for t in texts]

    def fits(self, value):
        return True


@pytest.fixture
def app_module():
    import legacy_flask_app as app_module

    return app_module


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(embeddings, "get_provider", lambda name=None: fake)
    return fake


@pytest.fixture
def client(app_module, tmp_path, monkeypatch):
    from models import Base, create_default_templates

    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    with app_module.SessionLocal() as session:
        create_default_templates(session)
    monkeypatch.setitem(app_module.app.config, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(scorer, "load_embedding_model", lambda: None)
    return app_module.app.test_client()


def _job(client, description=SAMPLE_JD):
    return client.post("/api/jobs", json={"title": "AI Engineer", "description_text": description}).get_json()


def _upload(client, job_id, path=RESUME):
    response = client.post(f"/api/candidates?job_id={job_id}", content_type="multipart/form-data",
                           data={"resume": (io.BytesIO(path.read_bytes()), path.name)})
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def _rows(app_module, model, **filters):
    with app_module.SessionLocal() as session:
        return session.query(model).filter_by(**filters).order_by(model.chunk_index).all()


def test_upload_stores_resume_chunks_with_embeddings(client, app_module, provider):
    job = _job(client)
    candidate = _upload(client, job["id"])
    rows = _rows(app_module, ResumeChunk, candidate_id=candidate["id"])
    with app_module.SessionLocal() as session:
        resume_text = session.get(Candidate, candidate["id"]).resume_text

    assert [r.section for r in rows] == ["header", "summary", "skills", "experience", "education"]
    assert [r.chunk_index for r in rows] == list(range(len(rows)))
    for row in rows:
        assert resume_text[row.char_start:row.char_end] == row.text  # citations can point at the source
        assert row.source_file == candidate["resume_filename"]
        assert row.embedding_model == "fake/3" and len(row.embedding) == 3
    skills = next(r for r in rows if r.section == "skills")
    assert f"Skills: {skills.text}" in provider.embedded  # the section label is part of what is embedded


def test_job_create_and_update_reindex_only_when_the_description_changes(client, app_module, provider):
    job = _job(client)
    first = _rows(app_module, JobChunk, job_id=job["id"])
    assert [r.section for r in first][:3] == ["summary", "summary", "about"]
    assert all(r.embedding for r in first)

    client.put(f"/api/jobs/{job['id']}", json={"title": "Renamed"})
    assert [r.id for r in _rows(app_module, JobChunk, job_id=job["id"])] == [r.id for r in first]

    client.put(f"/api/jobs/{job['id']}", json={"description_text": "REQUIREMENTS\n- Rust\n\nNICE TO HAVE\n- Go"})
    after = _rows(app_module, JobChunk, job_id=job["id"])
    assert [(r.section, r.text) for r in after] == [("requirements", "- Rust"), ("preferred", "- Go")]


def test_without_a_provider_chunks_are_stored_without_vectors(client, app_module, monkeypatch):
    def unavailable(name=None):
        raise EmbeddingUnavailable("no model")

    monkeypatch.setattr(embeddings, "get_provider", unavailable)
    job = _job(client)
    candidate = _upload(client, job["id"])
    rows = _rows(app_module, ResumeChunk, candidate_id=candidate["id"])
    assert len(rows) == 5 and all(r.embedding is None and r.embedding_model is None for r in rows)


def test_indexing_failure_never_fails_the_upload(client, app_module, monkeypatch, caplog):
    broken = FakeProvider(fail=MemoryError("boom"))  # not EmbeddingUnavailable: an unexpected crash
    monkeypatch.setattr(embeddings, "get_provider", lambda name=None: broken)
    job = _job(client)
    with caplog.at_level(logging.ERROR):
        candidate = _upload(client, job["id"])
    assert _rows(app_module, ResumeChunk, candidate_id=candidate["id"]) == []
    assert "--reindex" in caplog.text
    assert client.get(f"/api/candidates/{candidate['id']}").status_code == 200


def test_reindex_fills_gaps_and_never_duplicates(client, app_module, monkeypatch):
    def unavailable(name=None):
        raise EmbeddingUnavailable("no model")

    monkeypatch.setattr(embeddings, "get_provider", unavailable)
    job = _job(client)
    candidate = _upload(client, job["id"])

    fake = FakeProvider()
    with app_module.SessionLocal() as session:
        totals = indexing.reindex_all(session, fake)
        totals_again = indexing.reindex_all(session, fake)
    assert totals == totals_again
    assert totals["candidates"] == 1 and totals["jobs"] == 1 and totals["without_vectors"] == 0
    rows = _rows(app_module, ResumeChunk, candidate_id=candidate["id"])
    assert len(rows) == 5 and all(r.embedding_model == "fake/3" for r in rows)


def test_deleting_removes_chunks(client, app_module, provider):
    job = _job(client)
    other = _job(client)
    doomed = _upload(client, job["id"])
    kept = _upload(client, other["id"], REPO / "sample_resumes" / "resume_02_michael_chen.txt")
    assert _rows(app_module, ResumeChunk, candidate_id=doomed["id"])

    client.delete(f"/api/jobs/{job['id']}")
    assert _rows(app_module, ResumeChunk, candidate_id=doomed["id"]) == []
    assert _rows(app_module, JobChunk, job_id=job["id"]) == []
    assert _rows(app_module, ResumeChunk, candidate_id=kept["id"])

    client.delete(f"/api/candidates/{kept['id']}")
    assert _rows(app_module, ResumeChunk, candidate_id=kept["id"]) == []


def test_reindex_command(tmp_path, monkeypatch, capsys):
    url = f"sqlite:///{(tmp_path / 'cli.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(embeddings, "get_provider", lambda name=None: FakeProvider())
    from database import create_database_engine

    engine = create_database_engine(url)
    with Session(engine) as session:
        session.add(Job(title="J", description_text="REQUIREMENTS\n- Python"))
        session.commit()
    engine.dispose()

    assert indexing.main(["--reindex"]) == 0
    assert "Reindexed 0 candidates and 1 jobs: 1 chunks, 0 without vectors" in capsys.readouterr().out
    assert indexing.main([]) == 2  # no action given


@pytest.mark.slow
def test_real_model_embeds_every_chunk_whole(client, app_module, monkeypatch, tmp_path):
    monkeypatch.undo()  # restore the real embedding model (this also undoes the upload folder)
    monkeypatch.setitem(app_module.app.config, "UPLOAD_FOLDER", str(tmp_path))
    model = scorer.load_embedding_model()
    if model is None:
        pytest.skip("embedding model unavailable")
    job = _job(client)
    candidate = _upload(client, job["id"])
    rows = _rows(app_module, ResumeChunk, candidate_id=candidate["id"])
    assert rows and all(len(r.embedding) == 384 for r in rows)
    assert {r.embedding_model for r in rows} == {"sentence-transformers/all-MiniLM-L6-v2"}
    assert all(len(model.tokenizer(f"x: {r.text}")["input_ids"]) <= model.max_seq_length for r in rows)


# --- PostgreSQL + pgvector ----------------------------------------------------------

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL not set")
def test_pgvector_column_stores_and_searches_vectors():
    from database import create_database_engine

    name = f"hireai_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_database_engine(make_url(POSTGRES_URL).set(database=name).render_as_string(hide_password=False))
    try:
        with engine.connect() as conn:
            column_type = conn.execute(text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = 'resume_chunks'::regclass AND attname = 'embedding'")).scalar()
        assert column_type == "vector"

        with Session(engine) as session:
            job = Job(title="J", description_text="x")
            candidate = Candidate(name="C", job=job, resume_text="python rust")
            session.add(candidate)
            session.flush()
            for i, vector in enumerate(([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.7071, 0.7071, 0.0])):
                session.add(ResumeChunk(candidate_id=candidate.id, chunk_index=i, section="skills", text=f"c{i}",
                                        char_start=0, char_end=2, embedding=vector, embedding_model="fake/3"))
            session.commit()

            stored = session.query(ResumeChunk).order_by(ResumeChunk.chunk_index).all()
            assert [r.embedding for r in stored][0] == [1.0, 0.0, 0.0]  # read back as a plain list
            nearest = session.execute(text(
                "SELECT chunk_index FROM resume_chunks ORDER BY embedding <=> CAST(:q AS vector) LIMIT 2"),
                {"q": "[1, 0.1, 0]"}).scalars().all()
            assert nearest == [0, 2]  # cosine distance through pgvector's operator

            session.delete(candidate)  # ORM cascade
            session.commit()
            assert session.query(ResumeChunk).count() == 0
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
