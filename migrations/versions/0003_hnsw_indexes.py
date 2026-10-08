"""HNSW vector indexes for the default embedding model (PostgreSQL only).

The embedding column has no fixed dimension (vectors from several models can coexist),
but an HNSW index needs one. So each index is a partial expression index: it covers
rows from the default model only, cast to that model's dimension. Queries must use the
same expression, `(embedding::vector(384)) <=> ...`, for the planner to use it
(retrieval.py does). Rows from other models are still searchable, just without the index.

SQLite has no vector index; retrieval there uses brute-force cosine similarity.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-09
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DIMENSION = 384
TABLES = ("resume_chunks", "job_chunks")


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        # m=16, ef_construction=64 are pgvector's defaults, stated explicitly so a change is a visible decision.
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_embedding_hnsw_minilm ON {table} "
            f"USING hnsw ((embedding::vector({DIMENSION})) vector_cosine_ops) "
            f"WITH (m = 16, ef_construction = 64) "
            f"WHERE embedding_model = '{MODEL}'"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_embedding_hnsw_minilm")
