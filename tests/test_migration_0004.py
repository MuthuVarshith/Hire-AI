"""Migration 0004 (agent_shortlists): upgrade from 0003, the table's shape and constraints, and
downgrade back to 0003 without touching the other tables. SQLite always runs; PostgreSQL runs when
TEST_POSTGRES_URL is set (the `engine` fixture of test_migrations.py).
"""
import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

import database
from tests import test_migrations

engine = test_migrations.engine  # fixture: a fresh SQLite or PostgreSQL database

COLUMNS = {"id": False, "thread_id": False, "job_id": False, "request": False, "entries": False,
           "approved_by": False, "approved_at": False, "note": True}  # name -> nullable


def migrate(eng: Engine, direction: str, revision: str) -> None:
    with eng.begin() as conn:
        getattr(command, direction)(database.alembic_config(conn), revision)


def revision(eng: Engine) -> str | None:
    with eng.connect() as conn:
        return database.current_revision(conn)


def add_job(eng: Engine) -> int:
    with eng.begin() as conn:
        conn.execute(text("INSERT INTO jobs (title, description_text) VALUES ('Backend', 'Python')"))
        return int(conn.execute(text("SELECT MAX(id) FROM jobs")).scalar_one())


def add_shortlist(eng: Engine, job_id: int, thread_id: str) -> None:
    with eng.begin() as conn:
        conn.execute(text("INSERT INTO agent_shortlists (thread_id, job_id, request, entries, approved_by, "
                          "approved_at) VALUES (:t, :j, 'shortlist', '[]', 'Rita', CURRENT_TIMESTAMP)"),
                     {"t": thread_id, "j": job_id})


def test_0004_is_the_head_and_follows_0003():
    assert database.head_revision() == "0004"


def test_upgrade_from_0003_creates_the_table(engine):
    migrate(engine, "upgrade", "0003")
    assert "agent_shortlists" not in inspect(engine).get_table_names()
    migrate(engine, "upgrade", "0004")
    assert revision(engine) == "0004"

    inspector = inspect(engine)
    columns = {c["name"]: c["nullable"] for c in inspector.get_columns("agent_shortlists")}
    assert columns == COLUMNS
    assert [u["column_names"] for u in inspector.get_unique_constraints("agent_shortlists")] == [["thread_id"]]
    indexes = {i["name"]: i["column_names"] for i in inspector.get_indexes("agent_shortlists")}
    assert indexes.get("ix_agent_shortlists_job_id") == ["job_id"]
    (fk,) = inspector.get_foreign_keys("agent_shortlists")
    assert (fk["constrained_columns"], fk["referred_table"], fk["referred_columns"]) == (["job_id"], "jobs", ["id"])
    assert fk["options"].get("ondelete") == "CASCADE"
    assert test_migrations._schema_drift(engine) == []


def test_thread_id_is_unique(engine):
    database.upgrade_database(engine)
    job_id = add_job(engine)
    add_shortlist(engine, job_id, "t-1")
    with pytest.raises(IntegrityError):
        add_shortlist(engine, job_id, "t-1")


def test_downgrade_to_0003_drops_only_the_shortlists(engine):
    database.upgrade_database(engine)
    job_id = add_job(engine)
    add_shortlist(engine, job_id, "t-1")

    migrate(engine, "downgrade", "0003")
    assert revision(engine) == "0003"
    inspector = inspect(engine)
    assert "agent_shortlists" not in inspector.get_table_names()
    assert test_migrations.APP_TABLES <= set(inspector.get_table_names())
    with engine.connect() as conn:  # the jobs table and its rows are untouched
        assert conn.execute(text("SELECT title FROM jobs")).scalars().all() == ["Backend"]

    migrate(engine, "upgrade", "head")  # and the upgrade can run again
    assert revision(engine) == "0004" and test_migrations._schema_drift(engine) == []
    add_shortlist(engine, job_id, "t-1")  # the old row went with the table


def test_deleting_a_job_cascades_to_its_shortlists_where_foreign_keys_are_enforced(engine):
    if engine.dialect.name != "postgresql":
        pytest.skip("SQLite does not enforce foreign keys here (no PRAGMA foreign_keys)")
    database.upgrade_database(engine)
    job_id = add_job(engine)
    add_shortlist(engine, job_id, "t-1")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM jobs WHERE id = :j"), {"j": job_id})
        assert conn.execute(text("SELECT COUNT(*) FROM agent_shortlists")).scalar_one() == 0
