"""Resume and job-description chunks with embeddings, for retrieval.

On PostgreSQL the embedding column is pgvector's `vector` (the extension is enabled
here); elsewhere it is a JSON array. The column has no fixed dimension, so vectors from
different embedding models can coexist; each row records the model that produced it.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08 19:17:03.613275
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _embedding_type() -> sa.types.TypeEngine:
    # Self-contained on purpose: a migration must not import application models, which change later.
    if op.get_bind().dialect.name == "postgresql":
        from pgvector.sqlalchemy import Vector

        return Vector()
    return sa.JSON()


def _chunk_columns() -> list[sa.Column]:
    return [
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('section', sa.String(length=32), nullable=False),
        sa.Column('heading', sa.String(length=255), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('char_start', sa.Integer(), nullable=False),
        sa.Column('char_end', sa.Integer(), nullable=False),
    ]


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        'job_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        *_chunk_columns(),
        sa.Column('embedding', _embedding_type(), nullable=True),
        sa.Column('embedding_model', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'chunk_index', name='uq_job_chunks_job_index'),
    )
    op.create_index('ix_job_chunks_job_id', 'job_chunks', ['job_id'], unique=False)

    op.create_table(
        'resume_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('candidate_id', sa.Integer(), nullable=False),
        *_chunk_columns(),
        sa.Column('source_file', sa.String(length=255), nullable=True),
        sa.Column('embedding', _embedding_type(), nullable=True),
        sa.Column('embedding_model', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('candidate_id', 'chunk_index', name='uq_resume_chunks_candidate_index'),
    )
    op.create_index('ix_resume_chunks_candidate_id', 'resume_chunks', ['candidate_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_resume_chunks_candidate_id', table_name='resume_chunks')
    op.drop_table('resume_chunks')
    op.drop_index('ix_job_chunks_job_id', table_name='job_chunks')
    op.drop_table('job_chunks')
    # The vector extension is left installed: it is database-wide and may be used elsewhere.
