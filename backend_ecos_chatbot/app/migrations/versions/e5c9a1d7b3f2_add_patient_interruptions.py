"""add patient interruptions: chat_messages.interrupted_by and spoken_content

Revision ID: e5c9a1d7b3f2
Revises: d8b3e5f1a2c4
Create Date: 2026-11-17 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e5c9a1d7b3f2'
down_revision: Union[str, Sequence[str], None] = 'd8b3e5f1a2c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Réplique du patient coupée par l'étudiant : "voice" | "push_to_talk" | "button"
    op.add_column('chat_messages', sa.Column('interrupted_by', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    # Ce que le patient a réellement prononcé avant d'être coupé
    op.add_column('chat_messages', sa.Column('spoken_content', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chat_messages', 'spoken_content')
    op.drop_column('chat_messages', 'interrupted_by')
