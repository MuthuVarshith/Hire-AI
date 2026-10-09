"""Migration 0005: agent_decisions, and agent_shortlists kept as audit rows (job_id SET NULL plus a
job_title snapshot). Upgrade from 0004 with data, constraints, and downgrade back to 0004.
SQLite always runs; PostgreSQL runs when TEST_POSTGRES_URL is set.
"""
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

import database
from tests import test_migrations
from tests.test_migration_0004 import add_job, add_shortlist, migrate, revision

engine = test_migrations.engine  # fixture: a fresh SQLite or PostgreSQL database


def add_decision(eng, thread_id, job_id=None):
    with eng.begin() as conn:
        conn.execute(text("INSERT INTO agent_decisions (thread_id, decision, reviewer, decided_at, job_id) "
                          "VALUES (:t, 'approve', 'Rita', CURRENT_TIMESTAMP, :j)"), {"t": thread_id, "j": job_id})


def test_0005_is_the_head():
    assert database.head_revision() == "0005"


def test_upgrade_from_0004_keeps_shortlists_and_snapshots_the_job_title(engine):
    migrate(engine, "upgrade", "0004")
    job_id = add_job(engine)
    add_shortlist(engine, job_id, "t-1")
    migrate(engine, "upgrade", "0005")
    assert revision(engine) == "0005" and test_migrations._schema_drift(engine) == []

    inspector = inspect(engine)
    columns = {c["name"]: c["nullable"] for c in inspector.get_columns("agent_shortlists")}
    assert (columns["job_id"], columns["job_title"], columns["dropped_ids"]) == (True, True, True)
    (fk,) = inspector.get_foreign_keys("agent_shortlists")
    assert (fk["referred_table"], fk["options"].get("ondelete")) == ("jobs", "SET NULL")
    (decision_fk,) = inspector.get_foreign_keys("agent_decisions")
    assert decision_fk["options"].get("ondelete") == "SET NULL"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT thread_id, job_id, job_title FROM agent_shortlists")).all() == [
            ("t-1", job_id, "Backend")]


def test_decision_thread_id_is_unique(engine):
    database.upgrade_database(engine)
    add_decision(engine, "t-1")
    with pytest.raises(IntegrityError):
        add_decision(engine, "t-1")


def test_audit_rows_outlive_their_job_where_foreign_keys_are_enforced(engine):
    if engine.dialect.name != "postgresql":
        pytest.skip("SQLite does not enforce foreign keys here (no PRAGMA foreign_keys)")
    database.upgrade_database(engine)
    job_id = add_job(engine)
    add_shortlist(engine, job_id, "t-1")
    add_decision(engine, "t-1", job_id)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM jobs WHERE id = :j"), {"j": job_id})
        assert conn.execute(text("SELECT job_id FROM agent_shortlists")).all() == [(None,)]
        assert conn.execute(text("SELECT job_id FROM agent_decisions")).all() == [(None,)]


def test_downgrade_to_0004_restores_its_schema(engine):
    database.upgrade_database(engine)
    job_id = add_job(engine)
    add_shortlist(engine, job_id, "t-1")
    add_decision(engine, "t-1", job_id)
    migrate(engine, "downgrade", "0004")
    inspector = inspect(engine)
    assert "agent_decisions" not in inspector.get_table_names()
    columns = {c["name"]: c["nullable"] for c in inspector.get_columns("agent_shortlists")}
    assert "job_title" not in columns and columns["job_id"] is False
    (fk,) = inspector.get_foreign_keys("agent_shortlists")
    assert fk["options"].get("ondelete") == "CASCADE"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT thread_id FROM agent_shortlists")).scalars().all() == ["t-1"]
    migrate(engine, "upgrade", "head")
    assert test_migrations._schema_drift(engine) == []
