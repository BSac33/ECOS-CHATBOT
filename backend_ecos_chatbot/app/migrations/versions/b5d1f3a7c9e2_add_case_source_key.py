"""add clinical_cases.source_key (stations imported from a private pack)

Revision ID: b5d1f3a7c9e2
Revises: a3c7e9b2d4f6
Create Date: 2026-11-17 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b5d1f3a7c9e2'
down_revision: Union[str, Sequence[str], None] = 'a3c7e9b2d4f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clinical_cases', sa.Column('source_key', sa.String(), nullable=True))
    op.create_index(op.f('ix_clinical_cases_source_key'), 'clinical_cases', ['source_key'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_clinical_cases_source_key'), table_name='clinical_cases')
    op.drop_column('clinical_cases', 'source_key')
