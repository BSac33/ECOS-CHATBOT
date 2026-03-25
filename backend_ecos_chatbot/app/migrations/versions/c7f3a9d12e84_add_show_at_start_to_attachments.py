"""add show_at_start to attachments

Revision ID: c7f3a9d12e84
Revises: 58b69b0b70c9
Create Date: 2026-03-25 08:00:00.000000

Ajoute le champ show_at_start à la table attachments.
Ce champ indique que la pièce jointe (iconographie, ECG, radio, etc.)
doit être affichée dès le début de la station ECOS écrite,
sans nécessiter un mot-clé déclencheur.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7f3a9d12e84'
down_revision: Union[str, Sequence[str], None] = '58b69b0b70c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'attachments',
        sa.Column(
            'show_at_start',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false')
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('attachments', 'show_at_start')
