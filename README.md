# ECOS Chatbot

Plateforme d'entraînement aux ECOS (examens cliniques objectifs structurés) pour les
étudiants en médecine : l'étudiant mène la station face à un patient simulé par une IA (à
l'écrit ou à l'oral), puis reçoit une correction sur la grille de la station, relisible par
l'enseignant.

- **Étudiants** : stations d'interrogatoire, d'annonce, d'analyse de documents ; mode
  vocal (appuyer pour parler ou consultation mains libres) ; débriefing avec citations et
  contenu pédagogique ; export et suppression de ses données.
- **Enseignants** : atelier de création de stations (fiche structurée, vérifications,
  assistant fondé sur le référentiel officiel, versions publiées), test du patient,
  relecture et modification des corrections.
- **Modèles hébergés par l'établissement** : vLLM (Qwen) pour le patient, l'arbitre des
  messages et la correction ; Kyutai pour la voix. Aucune donnée n'est envoyée à un service
  tiers.

## Architecture

| Partie | Technologies | Dossier |
|---|---|---|
| API | FastAPI, SQLModel, PostgreSQL, Alembic | `backend_ecos_chatbot/app/` |
| Site | Vue 3, TypeScript, PrimeVue, Vite | `frontend/` |
| Modèles (GPU) | vLLM, Kyutai moshi-server, passerelle nginx | `deploy/dmz/`, `voice/` |

## Démarrer

```bash
# Développement (code monté, rechargement automatique)
make setup && make seed           # API :8000, site :5173

# Production : voir docs/DEPLOYMENT.md
docker compose -f docker-compose.prod.yml up -d --build
```

## Tests

```bash
cd backend_ecos_chatbot/app && pip install -r requirements-dev.txt && pytest && ruff check .
cd frontend && npm ci && npm run build && npm test
```

La CI GitHub (`.github/workflows/ci.yml`) lance aussi les migrations et les tests sur
PostgreSQL et construit les images.

## Documentation

`docs/DEPLOYMENT.md` (installation, sauvegardes, RGPD), `docs/EVALUATION.md` (correction
automatique et relecture), `docs/CASE_AUTHORING.md` (atelier), `docs/PATIENT_AGENT.md`,
`docs/VOICE.md`, `docs/BANC_ESSAI.md` (banc d'essai des modèles), `CLAUDE.md` (vue
d'ensemble technique).

## Contenus protégés

Le dépôt est public. Les stations issues d'ouvrages (packs privés) et les textes du
référentiel de cardiologie ne sont jamais versionnés : ils sont importés dans la base depuis
`backend_ecos_chatbot/app/private/` (ignoré par git) ou téléchargés à l'installation.

## Licence

Aucune licence n'a encore été choisie : sans licence, le code n'est pas réutilisable par
des tiers. Le choix revient aux auteurs et à leur établissement.
