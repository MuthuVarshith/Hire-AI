"""Shortlists proposed by the agent and approved by a human, with who approved and when.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_shortlists',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('thread_id', sa.String(length=64), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('request', sa.Text(), nullable=False),
        sa.Column('entries', sa.JSON(), nullable=False),
        sa.Column('approved_by', sa.String(length=255), nullable=False),
        sa.Column('approved_at', sa.DateTime(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('thread_id'),
    )
    op.create_index('ix_agent_shortlists_job_id', 'agent_shortlists', ['job_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_agent_shortlists_job_id', table_name='agent_shortlists')
    op.drop_table('agent_shortlists')
