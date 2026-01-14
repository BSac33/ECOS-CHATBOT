"""add_role_definition

Revision ID: 96cd36607078
Revises: ff23949a4733
Create Date: 2026-01-14 09:14:53.906696

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '96cd36607078'
down_revision: Union[str, Sequence[str], None] = 'ff23949a4733'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Vérifier si l'enum existe déjà
    connection = op.get_bind()
    result = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole')")
    ).scalar()
    
    if not result:
        # Créer l'enum seulement s'il n'existe pas
        op.execute("CREATE TYPE userrole AS ENUM ('student', 'teacher', 'admin')")
    
    # Ajouter la colonne role dans users (nullable au début)
    op.add_column('users', sa.Column('role', sa.Enum('student', 'teacher', 'admin', name='userrole'), nullable=True))
    
    # Attribuer les rôles aux utilisateurs existants selon is_superuser
    op.execute("""
        UPDATE users 
        SET role = CASE 
            WHEN is_superuser = true THEN 'admin'::userrole
            ELSE 'student'::userrole
        END
        WHERE role IS NULL
    """)
    
    # Rendre la colonne NOT NULL maintenant qu'elle est peuplée
    op.alter_column('users', 'role', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Supprimer la colonne role de users
    op.drop_column('users', 'role')
    
    # Supprimer l'enum type (optionnel)
    # op.execute("DROP TYPE IF EXISTS userrole")
