"""add case authoring (sheet, case_versions) and official corpus tables

Revision ID: f2a8c6e4d1b9
Revises: e5c9a1d7b3f2
Create Date: 2026-11-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f2a8c6e4d1b9'
down_revision: Union[str, Sequence[str], None] = 'e5c9a1d7b3f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

S = sqlmodel.sql.sqltypes.AutoString


def upgrade() -> None:
    """Upgrade schema."""
    # Fiche de cas structurée (brouillon de travail)
    op.add_column('clinical_cases', sa.Column('sheet', sa.JSON(), nullable=True))

    # Versions figées des cas
    op.create_table(
        'case_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', S(), nullable=False),
        sa.Column('sheet', sa.JSON(), nullable=False),
        sa.Column('title', S(), nullable=False),
        sa.Column('student_instructions', S(), nullable=False),
        sa.Column('scenario_context', S(), nullable=False),
        sa.Column('patient_prompt', S(), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('exam_findings', sa.JSON(), nullable=True),
        sa.Column('grid_items', sa.JSON(), nullable=False),
        sa.Column('total_points', sa.Float(), nullable=False),
        sa.Column('voice_id', S(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['clinical_cases.id'], ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_case_versions_case_id'), 'case_versions', ['case_id'], unique=False)
    op.create_index(op.f('ix_case_versions_status'), 'case_versions', ['status'], unique=False)

    # Tentatives : version jouée, tentative de test
    op.add_column('attempts', sa.Column('case_version_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_attempts_case_version_id', 'attempts', 'case_versions', ['case_version_id'], ['id'])
    op.add_column('attempts', sa.Column('is_test', sa.Boolean(), nullable=False, server_default=sa.false()))

    # Corpus officiel
    op.create_table(
        'corpus_sources',
        sa.Column('id', S(), nullable=False),
        sa.Column('title', S(), nullable=False),
        sa.Column('publisher', S(), nullable=False),
        sa.Column('license_note', S(), nullable=False),
        sa.Column('homepage', S(), nullable=True),
        sa.Column('retrieved_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'corpus_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', S(), nullable=False),
        sa.Column('url', S(), nullable=False),
        sa.Column('item_number', sa.Integer(), nullable=True),
        sa.Column('chapter_title', S(), nullable=False),
        sa.Column('section', S(), nullable=False),
        sa.Column('rank', S(), nullable=True),
        sa.Column('kind', S(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('text', S(), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['corpus_sources.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_corpus_chunks_source_id'), 'corpus_chunks', ['source_id'], unique=False)
    op.create_index(op.f('ix_corpus_chunks_item_number'), 'corpus_chunks', ['item_number'], unique=False)
    op.create_index(op.f('ix_corpus_chunks_kind'), 'corpus_chunks', ['kind'], unique=False)
    op.create_table(
        'starting_situations',
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('title', S(), nullable=False),
        sa.PrimaryKeyConstraint('number'),
    )
    op.create_table(
        'item_situation_links',
        sa.Column('item_number', sa.Integer(), nullable=False),
        sa.Column('situation_number', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('item_number', 'situation_number'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('item_situation_links')
    op.drop_table('starting_situations')
    op.drop_index(op.f('ix_corpus_chunks_kind'), table_name='corpus_chunks')
    op.drop_index(op.f('ix_corpus_chunks_item_number'), table_name='corpus_chunks')
    op.drop_index(op.f('ix_corpus_chunks_source_id'), table_name='corpus_chunks')
    op.drop_table('corpus_chunks')
    op.drop_table('corpus_sources')
    op.drop_column('attempts', 'is_test')
    op.drop_constraint('fk_attempts_case_version_id', 'attempts', type_='foreignkey')
    op.drop_column('attempts', 'case_version_id')
    op.drop_index(op.f('ix_case_versions_status'), table_name='case_versions')
    op.drop_index(op.f('ix_case_versions_case_id'), table_name='case_versions')
    op.drop_table('case_versions')
    op.drop_column('clinical_cases', 'sheet')
