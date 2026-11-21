"""index des tentatives (utilisateur, cas) et des messages (tentative, date)

Revision ID: c7e2a9d4f1b8
Revises: b5d1f3a7c9e2
Create Date: 2026-11-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c7e2a9d4f1b8'
down_revision: Union[str, Sequence[str], None] = 'b5d1f3a7c9e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_attempts_user_id'), 'attempts', ['user_id'], unique=False)
    op.create_index(op.f('ix_attempts_case_id'), 'attempts', ['case_id'], unique=False)
    op.create_index('ix_chat_messages_attempt_created', 'chat_messages', ['attempt_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_chat_messages_attempt_created', table_name='chat_messages')
    op.drop_index(op.f('ix_attempts_case_id'), table_name='attempts')
    op.drop_index(op.f('ix_attempts_user_id'), table_name='attempts')
