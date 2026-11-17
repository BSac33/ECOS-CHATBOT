"""add patient agent tools (exam_findings, examiner role) and moderation_events

Revision ID: c4f1a9e2b7d3
Revises: 58b69b0b70c9
Create Date: 2026-11-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c4f1a9e2b7d3'
down_revision: Union[str, Sequence[str], None] = '58b69b0b70c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nouveau rôle de message : informations données par l'examinateur.
    # ALTER TYPE ... ADD VALUE doit s'exécuter hors transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE chatrole ADD VALUE IF NOT EXISTS 'examiner'")

    # Résultats d'examen clinique structurés (outil resultat_examen_clinique)
    op.add_column('clinical_cases', sa.Column('exam_findings', sa.JSON(), nullable=True))

    # Traçabilité des écarts de l'étudiant
    op.create_table(
        'moderation_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('attempt_id', sa.Uuid(), nullable=False),
        sa.Column('message_id', sa.Uuid(), nullable=True),
        sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('category', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('severity', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('action', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('detail', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('student_message', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['attempt_id'], ['attempts.id'], ),
        sa.ForeignKeyConstraint(['message_id'], ['chat_messages.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_moderation_events_attempt_id'), 'moderation_events', ['attempt_id'], unique=False)
    op.create_index(op.f('ix_moderation_events_source'), 'moderation_events', ['source'], unique=False)
    op.create_index(op.f('ix_moderation_events_category'), 'moderation_events', ['category'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_moderation_events_category'), table_name='moderation_events')
    op.drop_index(op.f('ix_moderation_events_source'), table_name='moderation_events')
    op.drop_index(op.f('ix_moderation_events_attempt_id'), table_name='moderation_events')
    op.drop_table('moderation_events')
    op.drop_column('clinical_cases', 'exam_findings')
    # PostgreSQL ne permet pas de retirer une valeur d'enum : on supprime seulement
    # les messages "examiner" pour que l'ancien code puisse relire les transcripts.
    op.execute("DELETE FROM chat_messages WHERE role = 'examiner'")
