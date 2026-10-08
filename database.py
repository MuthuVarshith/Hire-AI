"""Database engine creation and schema migrations.

The schema is owned by Alembic (migrations/). On startup the app upgrades the
database to the latest revision. A database created by a version from before
migrations existed (tables present, no alembic_version table) is stamped at the
baseline revision, which describes exactly that schema, and then upgraded.
"""
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
BASELINE_REVISION = "0001"
_PRE_MIGRATION_TABLES = {"jobs", "candidates", "screening_results", "scoring_templates"}


def alembic_config(connection: Connection | None = None) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def head_revision() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert head is not None
    return head


def current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def upgrade_database(engine: Engine) -> None:
    """Bring the database to the latest schema revision."""
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        config = alembic_config(connection)
        if "alembic_version" not in tables and _PRE_MIGRATION_TABLES <= tables:
            logger.info("Adopting a database created before migrations: stamping revision %s", BASELINE_REVISION)
            command.stamp(config, BASELINE_REVISION)
        command.upgrade(config, "head")


def create_database_engine(database_url: str) -> Engine:
    """Create the engine for DATABASE_URL and migrate the schema to the latest revision."""
    engine = create_engine(database_url)
    upgrade_database(engine)
    return engine
