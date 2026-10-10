"""Database engine and the per-request session dependency (docs/contracts.md section 1).

The engine is created once at import from DATABASE_URL, and create_database_engine applies
the Alembic migrations, as the Flask app did. Routers and app/auth.py get a session with
`session: Session = Depends(get_session)`; it is closed after the response.
"""
import os
from collections.abc import Iterator

from sqlalchemy.orm import Session, sessionmaker

from database import create_database_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///recruiting_agent.db")
engine = create_database_engine(DATABASE_URL)  # applies migrations
SessionLocal = sessionmaker(bind=engine)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
