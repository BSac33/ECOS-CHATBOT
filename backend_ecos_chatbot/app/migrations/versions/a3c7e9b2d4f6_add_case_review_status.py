"""add optional peer review status on clinical cases

Revision ID: a3c7e9b2d4f6
Revises: f2a8c6e4d1b9
Create Date: 2026-11-17 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3c7e9b2d4f6'
down_revision: Union[str, Sequence[str], None] = 'f2a8c6e4d1b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clinical_cases', sa.Column('review_status', sa.String(), nullable=True))
    op.add_column('clinical_cases', sa.Column('review_requested_at', sa.DateTime(), nullable=True))
    op.add_column('clinical_cases', sa.Column('reviewed_by', sa.Integer(), nullable=True))
    op.add_column('clinical_cases', sa.Column('reviewed_at', sa.DateTime(), nullable=True))
    op.add_column('clinical_cases', sa.Column('review_note', sa.String(), nullable=True))
    op.add_column('clinical_cases', sa.Column('reviewed_sheet_hash', sa.String(), nullable=True))
    op.create_index(op.f('ix_clinical_cases_review_status'), 'clinical_cases', ['review_status'], unique=False)
    op.create_foreign_key('fk_clinical_cases_reviewed_by', 'clinical_cases', 'users', ['reviewed_by'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_clinical_cases_reviewed_by', 'clinical_cases', type_='foreignkey')
    op.drop_index(op.f('ix_clinical_cases_review_status'), table_name='clinical_cases')
    for column in ('reviewed_sheet_hash', 'review_note', 'reviewed_at', 'reviewed_by',
                   'review_requested_at', 'review_status'):
        op.drop_column('clinical_cases', column)
