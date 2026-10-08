"""Alembic migrations: the migrated schema matches the models, and older databases are adopted.

SQLite always runs. PostgreSQL runs when TEST_POSTGRES_URL points at a server
(e.g. postgresql+psycopg://hireai:hireai@localhost:5433/postgres); each test gets
its own throwaway database.
"""
import os
import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

import database
import models

APP_TABLES = {"jobs", "candidates", "screening_results", "scoring_templates"}
POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")


@pytest.fixture(params=["sqlite", "postgresql"])
def engine(request, tmp_path) -> Iterator[Engine]:
    if request.param == "sqlite":
        eng = create_engine(f"sqlite:///{(tmp_path / 'm.db').as_posix()}")
        yield eng
        eng.dispose()
        return

    if not POSTGRES_URL:
        pytest.skip("TEST_POSTGRES_URL not set")
    name = f"hireai_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    eng = create_engine(make_url(POSTGRES_URL).set(database=name))
    yield eng
    eng.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin.dispose()


def _schema_drift(eng: Engine) -> list:
    with eng.connect() as conn:
        return compare_metadata(MigrationContext.configure(conn), models.Base.metadata)


def _revision(eng: Engine) -> str | None:
    with eng.connect() as conn:
        return database.current_revision(conn)


def test_upgrade_on_empty_database_matches_models(engine):
    database.upgrade_database(engine)
    assert _revision(engine) == database.head_revision()
    assert APP_TABLES <= set(inspect(engine).get_table_names())
    assert _schema_drift(engine) == []


def test_upgrade_is_idempotent(engine):
    database.upgrade_database(engine)
    database.upgrade_database(engine)
    assert _revision(engine) == database.head_revision()


def test_adopts_database_created_before_migrations(engine):
    # What older versions did on startup: create_all with the four tables that existed then.
    models.Base.metadata.create_all(engine, tables=[models.Base.metadata.tables[t] for t in sorted(APP_TABLES)])
    with Session(engine) as session:
        models.create_default_templates(session)
        job = models.Job(title="Existing job", description_text="Python")
        session.add(job)
        session.flush()
        session.add(models.Candidate(name="Existing candidate", job_id=job.id))
        session.commit()
    assert "alembic_version" not in inspect(engine).get_table_names()

    database.upgrade_database(engine)

    assert _revision(engine) == database.head_revision()
    assert _schema_drift(engine) == []
    with Session(engine) as session:  # nothing was recreated or lost
        assert [j.title for j in session.query(models.Job)] == ["Existing job"]
        assert [c.name for c in session.query(models.Candidate)] == ["Existing candidate"]
        assert session.query(models.ScoringTemplate).count() == 5


def test_downgrade_to_base_and_back(engine):
    database.upgrade_database(engine)
    with engine.begin() as conn:
        command.downgrade(database.alembic_config(conn), "base")
    assert not APP_TABLES & set(inspect(engine).get_table_names())
    database.upgrade_database(engine)  # would fail on PostgreSQL if the enum type were left behind
    assert _schema_drift(engine) == []
