"""added_role_handling

Revision ID: bf9f8010f38b
Revises: 96cd36607078
Create Date: 2026-01-14 09:33:52.478132

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'bf9f8010f38b'
down_revision: Union[str, Sequence[str], None] = '96cd36607078'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()
    
    # Vérifier si l'enum existe déjà
    enum_exists = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole')")
    ).scalar()
    
    if not enum_exists:
        # Créer l'enum seulement s'il n'existe pas
        op.execute("CREATE TYPE userrole AS ENUM ('student', 'teacher', 'admin')")
    
    # Vérifier si la colonne role existe déjà
    column_exists = connection.execute(
        sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'role'
            )
        """)
    ).scalar()
    
    if not column_exists:
        # 1. Ajouter la colonne role dans users (nullable au début)
        op.add_column('users', sa.Column('role', sa.Enum('student', 'teacher', 'admin', name='userrole'), nullable=True))
        
        # 2. Attribuer les rôles par défaut selon is_superuser
        op.execute("""
            UPDATE users 
            SET role = CASE 
                WHEN is_superuser = true THEN 'admin'::userrole
                ELSE 'student'::userrole
            END
            WHERE role IS NULL
        """)
        
        # 3. Rendre la colonne NOT NULL maintenant qu'elle est peuplée
        op.alter_column('users', 'role', nullable=False)
    
    # Vérifier si l'index existe déjà
    index_exists = connection.execute(
        sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE tablename = 'users' AND indexname = 'ix_users_role'
            )
        """)
    ).scalar()
    
    if not index_exists:
        # 4. Créer un index sur la colonne role pour les requêtes
        op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Supprimer l'index et la colonne role
    op.drop_index(op.f('ix_users_role'), table_name='users')
    op.drop_column('users', 'role')
    
    # Optionnel : supprimer l'enum (commenté pour éviter les conflits si d'autres tables l'utilisent)
    # op.execute("DROP TYPE IF EXISTS userrole")
