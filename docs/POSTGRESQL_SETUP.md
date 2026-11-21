# Guide d'installation et configuration PostgreSQL

Ce guide explique comment installer et configurer PostgreSQL pour ECOS Chatbot.

## Installation de PostgreSQL

### macOS (avec Homebrew)
```bash
# Installation
brew install postgresql@15

# Démarrage du service
brew services start postgresql@15

# Vérification
psql --version
```

### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### Windows
Téléchargez et installez depuis: https://www.postgresql.org/download/windows/

## Configuration de la base de données

### 1. Connexion à PostgreSQL
```bash
# Se connecter en tant que superutilisateur
sudo -u postgres psql
# ou sur macOS:
psql postgres
```

### 2. Création de l'utilisateur et de la base
```sql
-- Créer l'utilisateur
CREATE USER ecos_user WITH PASSWORD 'ecos_password';

-- Créer la base de données
CREATE DATABASE ecos_chatbot OWNER ecos_user;

-- Donner tous les privilèges
GRANT ALL PRIVILEGES ON DATABASE ecos_chatbot TO ecos_user;

-- Quitter
\q
```

### 3. Vérification de la connexion
```bash
psql -U ecos_user -d ecos_chatbot -h localhost
```

## Configuration de l'application (hors Docker)

En temps normal, PostgreSQL tourne dans Docker (`docker-compose.yml` en développement,
`docker-compose.prod.yml` en production : voir `docs/DEPLOYMENT.md`). Pour lancer l'API à la
main contre une base locale :

```bash
cd backend_ecos_chatbot
cp fastapi.env.production.example fastapi.env
# éditer : DATABASE_URL=postgresql://ecos_user:<mot de passe>@localhost:5432/ecos_chatbot
#          SECRET_KEY=$(openssl rand -hex 32), VLLM_* (modèles), CORS_ORIGINS, SECURE_COOKIES=False

cd app
pip install -r requirements.txt
alembic upgrade head                                   # crée les tables
python scripts/create_user.py admin --role admin       # premier compte
python seed_database.py                                # cas d'exemple (base vide seulement)
DOCS_ENABLED=true uvicorn main:app --reload            # documentation sur /docs
```

- API : http://localhost:8000 ; supervision : http://localhost:8000/health
- Documentation interactive (`/docs`, `/redoc`) : seulement avec `DOCS_ENABLED=true`
- Taille du pool de connexions par processus : `DB_POOL_SIZE` (10), `DB_MAX_OVERFLOW` (20),
  `DB_POOL_TIMEOUT` (30 s). Total à garder sous `max_connections` de PostgreSQL (100 par
  défaut) : nombre de workers × (taille + débord).

## Commandes utiles PostgreSQL

### Se connecter à la base
```bash
psql -U ecos_user -d ecos_chatbot
```

### Commandes dans psql
```sql
-- Lister les tables
\dt

-- Voir la structure d'une table
\d clinical_cases

-- Compter les cas cliniques
SELECT COUNT(*) FROM clinical_cases;

-- Voir tous les cas
SELECT case_id, title, discipline FROM clinical_cases;

-- Voir la grille d'évaluation d'un cas
SELECT category, description, points 
FROM evaluation_items 
WHERE case_id = (SELECT id FROM clinical_cases WHERE case_id = 'appendicite_001')
ORDER BY "order";

-- Voir les sessions
SELECT session_id, started_at, is_ended FROM sessions;

-- Quitter
\q
```

### Réinitialiser la base (ATTENTION: perte de données)
```bash
python -c "from Backend.database import drop_tables, create_tables; drop_tables(); create_tables()"
python Backend/init_db.py
```

## Dépannage

### Problème de connexion
1. Vérifiez que PostgreSQL est démarré:
   ```bash
   # macOS
   brew services list
   
   # Linux
   sudo systemctl status postgresql
   ```

2. Vérifiez les paramètres de connexion dans `.env`

3. Vérifiez que l'utilisateur a les bons privilèges:
   ```sql
   \du  -- Liste les utilisateurs et leurs rôles
   ```

### Erreur "relation does not exist"
Les tables n'ont pas été créées. Exécutez:
```bash
python Backend/init_db.py
```

### Erreur "password authentication failed"
Vérifiez le mot de passe dans le fichier `.env` ou recréez l'utilisateur.

## Structure de la base

### Tables principales
- `clinical_cases`: Cas cliniques (titre, discipline, prompts, etc.)
- `evaluation_items`: Items de la grille d'évaluation
- `sessions`: Sessions d'examen
- `messages`: Messages échangés dans chaque session

### Relations
- Un `clinical_case` a plusieurs `evaluation_items` (1-N)
- Un `clinical_case` a plusieurs `sessions` (1-N)
- Une `session` a plusieurs `messages` (1-N)
