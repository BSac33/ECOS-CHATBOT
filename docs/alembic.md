# Créer une migration Alembic

## 1 - Générer une migration automatique 

```zsh
docker exec -it fastapi alembic revision --autogenerate -m "added_role_handling"
```

Génère un fichier "migrations", mais conflit psosible entre les élements déjà présents dans la collection d'origine qui ne contiennent pas l'élement nouveau.

Workaround: **rendre la colonne "nullable", puis attribuer une valeur par défaut** avant de migrer

```python
def upgrade() -> None:
    # 1. Ajouter nullable
    op.add_column('users', sa.Column('roles', sa.String(), nullable=True))
    
    # 2. Valeur par défaut
    op.execute("UPDATE users SET roles = 'student' WHERE roles IS NULL")
    
    # 3. Rendre NOT NULL
    op.alter_column('users', 'roles', nullable=False)
```

## 2 - Réaliser la migration

```zsh
cd "/Users/benjaminsacristan/Code Projects/ECOS CHATBOT/backend_ecos_chatbot" && docker exec -it fastapi alembic revision --autogenerate -m "add_hashed_password_to_user"
```

Réponse attendue: 

```zsh
  Generating
  /app/migrations/versions/ff23949a4733_add_hashed_password_to_user.py ...  done
```
Puis 

```zsh
cd "/Users/benjaminsacristan/Code Projects/ECOS CHATBOT/backend_ecos_chatbot" && docker exec -it fastapi alembic upgrade head
```