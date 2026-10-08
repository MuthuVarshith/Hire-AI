"""Baseline schema: the four tables the app created with create_all before migrations existed.

Databases created by those versions are stamped at this revision (see database.py)
instead of being recreated.

Revision ID: 0001
Revises: (none)
Create Date: 2026-10-08 18:52:38.008893
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('scoring_templates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('semantic_weight', sa.Float(), nullable=True),
    sa.Column('skill_weight', sa.Float(), nullable=True),
    sa.Column('experience_weight', sa.Float(), nullable=True),
    sa.Column('education_weight', sa.Float(), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description_text', sa.Text(), nullable=False),
    sa.Column('required_skills', sa.JSON(), nullable=True),
    sa.Column('preferred_skills', sa.JSON(), nullable=True),
    sa.Column('min_experience_years', sa.Float(), nullable=True),
    sa.Column('required_education', sa.String(length=100), nullable=True),
    sa.Column('responsibilities', sa.JSON(), nullable=True),
    sa.Column('scoring_template_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['scoring_template_id'], ['scoring_templates.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('candidates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('resume_filename', sa.String(length=255), nullable=True),
    sa.Column('resume_text', sa.Text(), nullable=True),
    sa.Column('skills', sa.JSON(), nullable=True),
    sa.Column('experience_years', sa.Float(), nullable=True),
    sa.Column('education', sa.JSON(), nullable=True),
    sa.Column('work_history', sa.JSON(), nullable=True),
    sa.Column('job_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.Enum('SCREENED', 'SHORTLISTED', 'INTERVIEW', 'OFFER', 'HIRED', 'REJECTED', name='pipelinestatus'), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('screening_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('candidate_id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('scoring_template_id', sa.Integer(), nullable=True),
    sa.Column('composite_score', sa.Float(), nullable=True),
    sa.Column('semantic_score', sa.Float(), nullable=True),
    sa.Column('skill_match_score', sa.Float(), nullable=True),
    sa.Column('experience_score', sa.Float(), nullable=True),
    sa.Column('education_score', sa.Float(), nullable=True),
    sa.Column('matched_skills', sa.JSON(), nullable=True),
    sa.Column('missing_skills', sa.JSON(), nullable=True),
    sa.Column('matched_preferred_skills', sa.JSON(), nullable=True),
    sa.Column('reasoning', sa.Text(), nullable=True),
    sa.Column('strengths', sa.JSON(), nullable=True),
    sa.Column('skill_gaps', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.ForeignKeyConstraint(['scoring_template_id'], ['scoring_templates.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('screening_results')
    op.drop_table('candidates')
    op.drop_table('jobs')
    op.drop_table('scoring_templates')
    # PostgreSQL keeps the enum type after its table is dropped; remove it so upgrade can recreate it.
    sa.Enum(name='pipelinestatus').drop(op.get_bind(), checkfirst=True)
