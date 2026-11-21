# Environnement de DÉVELOPPEMENT (docker-compose.yml : code monté, rechargement automatique).
# Production : docker-compose.prod.yml, voir docs/DEPLOYMENT.md.
COMPOSE ?= docker compose
DB_DIR := backend_ecos_chatbot/data/postgres

.PHONY: help setup reset seed corpus stations db-shell logs stop clean test backend-test frontend-test lint

help:
	@echo "ECOS Chatbot - commandes de développement"
	@echo ""
	@echo "  make setup         Démarre la base, les migrations, l'API et le frontend"
	@echo "  make seed          Remplit la base avec les cas d'exemple (refuse s'il y a des tentatives d'étudiants)"
	@echo "  make corpus        Importe le référentiel de cardiologie (CNEC/SFC) pour l'atelier"
	@echo "  make stations      Importe les packs privés (backend_ecos_chatbot/app/private/stations/)"
	@echo "  make reset         Supprime la base de développement, redémarre et seed"
	@echo "  make db-shell      Shell PostgreSQL"
	@echo "  make logs          Journaux en continu"
	@echo "  make stop          Arrête les services"
	@echo "  make clean         Arrête et supprime conteneurs, volumes et base de développement"
	@echo "  make backend-test  Tests du backend (SQLite en mémoire, modèles simulés)"
	@echo "  make frontend-test Vérification des types, build et tests du frontend"
	@echo "  make lint          Analyse statique du backend (ruff)"
	@echo "  make test          Parcours CLI (liste des cas, aide pour jouer une station)"

setup:
	$(COMPOSE) up -d --build
	@echo "API : http://localhost:8000   Frontend : http://localhost:5173"
	@echo "Exemples : make seed"

seed:
	$(COMPOSE) exec fastapi python seed_database.py

corpus:
	$(COMPOSE) exec fastapi python scripts/ingest_corpus.py

stations:
	$(COMPOSE) exec fastapi python scripts/import_stations.py

reset:
	$(COMPOSE) down
	rm -rf $(DB_DIR)
	$(COMPOSE) up -d --build --wait database fastapi
	$(COMPOSE) exec fastapi python seed_database.py
	$(COMPOSE) up -d

db-shell:
	$(COMPOSE) exec database sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

logs:
	$(COMPOSE) logs -f

stop:
	$(COMPOSE) down

clean:
	$(COMPOSE) down -v
	rm -rf $(DB_DIR)

backend-test:
	cd backend_ecos_chatbot/app && python -m pytest -q

frontend-test:
	cd frontend && npm ci && npm run build && npm test

lint:
	cd backend_ecos_chatbot/app && ruff check .

test:
	python ecos_cli.py health
	python ecos_cli.py list-cases
	@echo "Jouer une station : python ecos_cli.py chat-loop <id>"
	@echo "Puis : python ecos_cli.py attempt-finalize <attempt_id> && python ecos_cli.py attempt-evaluate <attempt_id>"
