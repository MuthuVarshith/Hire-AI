"""Sign-in: users, server-side sessions, and the signed-in reviewer on agent decisions.

- users: unique username, an argon2id password hash, role "admin" or "recruiter".
- sessions: the SHA-256 hash of each bearer token (never the token) and its expiry; deleted on logout.
- agent_decisions.reviewer_id: the user who approved or rejected, NULL for older rows (and SET NULL if
  the user is deleted, so the decision stays as an audit row with the reviewer's name).

Batch mode adds and drops the column on SQLite (it recreates the table); on PostgreSQL the same calls
are plain ALTER TABLE statements.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REVIEWER_FK = 'fk_agent_decisions_reviewer_id'
REVIEWER_INDEX = 'ix_agent_decisions_reviewer_id'


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'recruiter')", name='ck_users_role'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )
    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index('ix_sessions_user_id', 'sessions', ['user_id'], unique=False)

    with op.batch_alter_table('agent_decisions') as batch:
        batch.add_column(sa.Column('reviewer_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(REVIEWER_FK, 'users', ['reviewer_id'], ['id'], ondelete='SET NULL')
        batch.create_index(REVIEWER_INDEX, ['reviewer_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('agent_decisions') as batch:
        batch.drop_index(REVIEWER_INDEX)
        batch.drop_constraint(REVIEWER_FK, type_='foreignkey')
        batch.drop_column('reviewer_id')
    op.drop_index('ix_sessions_user_id', table_name='sessions')
    op.drop_table('sessions')
    op.drop_table('users')
