"""add voice mode: chat_messages.modality and clinical_cases.voice_id

Revision ID: d8b3e5f1a2c4
Revises: c4f1a9e2b7d3
Create Date: 2026-11-17 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd8b3e5f1a2c4'
down_revision: Union[str, Sequence[str], None] = 'c4f1a9e2b7d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # "text" ou "voice" ; les messages existants sont des messages écrits
    op.add_column('chat_messages', sa.Column(
        'modality', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='text'))
    # Voix du patient (chemin dans kyutai/tts-voices)
    op.add_column('clinical_cases', sa.Column('voice_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('clinical_cases', 'voice_id')
    op.drop_column('chat_messages', 'modality')
