"""Record every agent shortlist decision, and keep shortlists as audit rows when jobs are deleted.

- agent_decisions: one row per decision (approve or reject) with a UNIQUE thread_id. The app
  inserts it before resuming the paused run, so two decisions sent together can't both win.
- agent_shortlists: job_id becomes nullable with ON DELETE SET NULL (was CASCADE), plus a
  job_title snapshot and the ids of proposed candidates deleted before approval.

0004 is left unchanged, because a local database may already be at 0004.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 0004 created the job foreign key without a name. PostgreSQL named it agent_shortlists_job_id_fkey;
# on SQLite, batch mode reflects it under this naming convention so it can be dropped by name.
PG_DEFAULT_FK = 'agent_shortlists_job_id_fkey'
NAMED_FK = 'fk_agent_shortlists_job_id'
NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s"}


def _job_foreign_key(drop: str, create: str, ondelete: str, nullable: bool) -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(drop, 'agent_shortlists', type_='foreignkey')
        op.alter_column('agent_shortlists', 'job_id', existing_type=sa.Integer(), nullable=nullable)
        op.create_foreign_key(create, 'agent_shortlists', 'jobs', ['job_id'], ['id'], ondelete=ondelete)
        return
    with op.batch_alter_table('agent_shortlists', naming_convention=NAMING) as batch:
        batch.drop_constraint(NAMED_FK, type_='foreignkey')
        batch.alter_column('job_id', existing_type=sa.Integer(), nullable=nullable)
        batch.create_foreign_key(NAMED_FK, 'jobs', ['job_id'], ['id'], ondelete=ondelete)


def upgrade() -> None:
    op.create_table(
        'agent_decisions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('thread_id', sa.String(length=64), nullable=False),
        sa.Column('decision', sa.String(length=16), nullable=False),
        sa.Column('reviewer', sa.String(length=255), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=True),
        sa.Column('job_title', sa.String(length=255), nullable=True),
        sa.Column('request', sa.Text(), nullable=True),
        sa.Column('entries', sa.JSON(), nullable=True),
        sa.Column('outcome', sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('thread_id'),
    )
    op.create_index('ix_agent_decisions_job_id', 'agent_decisions', ['job_id'], unique=False)

    op.add_column('agent_shortlists', sa.Column('job_title', sa.String(length=255), nullable=True))
    op.add_column('agent_shortlists', sa.Column('dropped_ids', sa.JSON(), nullable=True))
    op.execute("UPDATE agent_shortlists SET job_title = "
               "(SELECT jobs.title FROM jobs WHERE jobs.id = agent_shortlists.job_id)")
    _job_foreign_key(drop=PG_DEFAULT_FK, create=NAMED_FK, ondelete='SET NULL', nullable=True)


def downgrade() -> None:
    # 0004 requires a job: shortlists whose job was deleted can't be kept under its schema.
    op.execute("DELETE FROM agent_shortlists WHERE job_id IS NULL")
    _job_foreign_key(drop=NAMED_FK, create=PG_DEFAULT_FK, ondelete='CASCADE', nullable=False)
    with op.batch_alter_table('agent_shortlists') as batch:
        batch.drop_column('dropped_ids')
        batch.drop_column('job_title')
    op.drop_index('ix_agent_decisions_job_id', table_name='agent_decisions')
    op.drop_table('agent_decisions')
