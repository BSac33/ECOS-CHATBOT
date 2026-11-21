# Déploiement

Deux parties indépendantes :

| Partie | Fichier | Où | GPU |
|---|---|---|---|
| Application : site, API, PostgreSQL | `docker-compose.prod.yml` | serveur web (ou poste local) | non |
| Modèles : vLLM patient + arbitre, Kyutai STT/TTS, passerelle | `deploy/dmz/docker-compose.yml` | machine GPU de la DMZ | oui |

L'application appelle les modèles en HTTPS / WSS à travers la passerelle de la DMZ (une clé
d'API, liste d'IP). Sans modèles joignables, le site fonctionne (connexion, stations, atelier,
référentiel) mais le patient ne répond pas : l'API renvoie une erreur 502 explicite.

## 1. Application

```bash
cp backend_ecos_chatbot/fastapi.env.production.example backend_ecos_chatbot/fastapi.env
cp backend_ecos_chatbot/postgres.env.example backend_ecos_chatbot/postgres.env
# éditer : mot de passe PostgreSQL (le même dans DATABASE_URL), SECRET_KEY (openssl rand -hex 32),
# URL et clé des modèles (section 3), CORS_ORIGINS, SECURE_COOKIES

docker compose -f docker-compose.prod.yml up -d --build
```

Services : `database` (PostgreSQL 16), `migrate` (Alembic à chaque démarrage, idempotent),
`api` (FastAPI, `API_WORKERS` processus, utilisateur sans privilèges), `web` (nginx :
frontend compilé + passerelle vers l'API). Le site est publié sur
`http://127.0.0.1:${WEB_PORT:-8080}`, c'est-à-dire **sur la machine seulement** : le reverse
proxy HTTPS de l'établissement s'y branche. Pour l'ouvrir au réseau (tests, sans HTTPS) :
`WEB_BIND=0.0.0.0` dans l'environnement de `docker compose`.

nginx (`frontend/nginx.conf`) sert l'application monopage et relaie :

- `/api/` vers l'API (préfixe retiré), délai de 10 min (correction automatique) ;
- `/chat/attempts/` sans tampon (flux SSE du patient, WebSocket du mode vocal, 1 h) ;
- `/attachments/` (documents de vignette, ECG, imagerie : un étudiant ne reçoit que ceux
  qui lui ont été montrés) ;
- `/health` (supervision : API et base joignables).

Il ajoute les en-têtes de sécurité (`frontend/security_headers.inc` : CSP, refus de
l'affichage en cadre, micro limité au site) et limite le débit : 30 essais de connexion par
minute et par adresse, 50 requêtes d'API par seconde ; au-delà, 429. L'adresse réelle du
client est reprise de `X-Forwarded-For` quand la requête vient d'un réseau privé (reverse
proxy). L'API refuse en plus 5 mots de passe faux par identifiant en 15 min.

En production, placer un reverse proxy HTTPS devant `web` et mettre `SECURE_COOKIES=True`.
Le micro du navigateur (mode vocal) n'est autorisé qu'en HTTPS ou sur `localhost`.

### Comptes

```bash
docker compose -f docker-compose.prod.yml exec -u ecos api python scripts/create_user.py admin --role admin
docker compose -f docker-compose.prod.yml exec -u ecos api python scripts/create_user.py dupont --role teacher --full-name "Dr Dupont"
# sans saisie : -e ECOS_PASSWORD=... ; compte existant : --reset-password
```

Les comptes ne se créent pas depuis le site : seul un administrateur peut en créer
(script ci-dessus, ou `POST /auth/create-user` connecté en administrateur). Chaque
utilisateur peut exporter ses données et supprimer son compte (page « Mon compte ») ; un
enseignant auteur de stations ne peut pas supprimer le sien (transfert par un
administrateur).

### Stations et référentiel

```bash
# Cas d'exemple + packs privés de backend_ecos_chatbot/app/private/stations/ (monté en lecture seule)
# ATTENTION : le seed vide d'abord les cas, tentatives et évaluations (installation initiale
# seulement) ; il refuse s'il trouve des tentatives d'étudiants (--force pour passer outre)
docker compose -f docker-compose.prod.yml exec -u ecos api python seed_database.py

# Pack privé ajouté ou mis à jour plus tard, sans rien effacer (idempotent : copier le pack
# dans private/stations/ puis importer tous les packs)
docker compose -f docker-compose.prod.yml exec -u ecos api python scripts/import_stations.py

# Référentiel officiel de cardiologie (CNEC/SFC) pour l'assistant de rédaction
docker compose -f docker-compose.prod.yml exec -u ecos api python scripts/ingest_corpus.py
```

Les packs privés (contenu du livre) et les textes du référentiel ne sont jamais dans l'image
ni dans git : le dépôt est public.

## 2. Modèles sur la DMZ

Voir `deploy/dmz/README.md` : modes d'accès, GPU partagé, certificats, mode sans accès sortant.

```bash
cd deploy/dmz
cp .env.example .env        # MODELS_API_KEY, MODELS_BIND (adresse interne), GPU
docker compose up -d --build
```

Deux modes d'accès, choisis dans `.env` :

- **direct** (défaut de `.env.example`) : pas de nginx, les ports des modèles sont publiés
  sur l'adresse interne de la machine seulement (`MODELS_BIND`), clé vLLM, sans TLS. Pour
  tester depuis un poste relié par VPN, ou derrière un nginx déjà en place (`127.0.0.1`).
- **passerelle** (profil `passerelle`) : nginx en conteneur, HTTPS, clé unique, liste d'IP.

Profils Compose : `llm` (vLLM dans Docker, défaut), `voix` (Kyutai), `passerelle` (nginx).
Si la partition de Docker manque de place et sans droits administrateur, les LLM tournent hors
Docker avec `deploy/dmz/vllm-local.sh` (même `.env`, mêmes adresses) et Docker ne sert qu'à la
voix (`COMPOSE_PROFILES=voix`). Version de vLLM et image vocale selon le pilote NVIDIA :
CUDA 12.4 → vLLM 0.8.5.post1 et `KYUTAI_CUDA_VERSION=12.4.1`.

Budget mémoire sur une L40S 48 Go : patient 0,55 (~26 Go) + arbitre 0,25 (~12 Go) +
STT ~2,5 Go + TTS ~5,3 Go. Le mode vocal est un profil Compose (`COMPOSE_PROFILES=voix`).

## 3. Relier l'application aux modèles

Dans `backend_ecos_chatbot/fastapi.env` (clé = `MODELS_API_KEY` de la DMZ).

Mode direct (tests par VPN) :

```bash
VLLM_BASE_URL=http://<adresse-interne>:8001/v1
VLLM_API_KEY=<clé>
VLLM_ARBITER_BASE_URL=http://<adresse-interne>:8002/v1
VLLM_ARBITER_API_KEY=<clé>
KYUTAI_STT_URL=ws://<adresse-interne>:8090
KYUTAI_TTS_URL=ws://<adresse-interne>:8089
KYUTAI_API_KEY=<MODELS_API_KEY>
```

Passerelle ou nginx existant (HTTPS) :

```bash
VLLM_BASE_URL=https://modeles.ihu.local/patient/v1
VLLM_API_KEY=<clé>
VLLM_ARBITER_BASE_URL=https://modeles.ihu.local/arbitre/v1
VLLM_ARBITER_API_KEY=<clé>
KYUTAI_STT_URL=wss://modeles.ihu.local/stt
KYUTAI_TTS_URL=wss://modeles.ihu.local/tts
KYUTAI_API_KEY=<clé>
```

Puis `docker compose -f docker-compose.prod.yml up -d` (le conteneur `api` relit `fastapi.env`
quand il est recréé).

### Application sur un poste local (tests)

`fastapi.env` : `CORS_ORIGINS=http://localhost:8080`, `SECURE_COOKIES=False`. Lancer avec
`WEB_PORT=127.0.0.1:8080` pour que le site ne soit joignable que depuis le poste. Le micro
du navigateur fonctionne sur `http://localhost` (contexte sécurisé). Si la machine de modèles
a une adresse en 172.16-31.x.x et reste injoignable depuis le conteneur `api` alors qu'elle
répond depuis le poste, changer les plages d'adresses de Docker (`default-address-pools`).

### Certificat de la PKI interne

Si le certificat de la passerelle est signé par l'AC de l'IHU, le conteneur `api` doit lui
faire confiance. Le client OpenAI (httpx) et le client Kyutai (websockets) lisent tous deux
`SSL_CERT_FILE` :

```bash
docker compose -f docker-compose.prod.yml exec api cat /etc/ssl/certs/ca-certificates.crt > backend_ecos_chatbot/ca-bundle.pem
cat ac-ihu.pem >> backend_ecos_chatbot/ca-bundle.pem
```

Décommenter le volume `ca-bundle.pem` du service `api` dans `docker-compose.prod.yml`, ajouter
`SSL_CERT_FILE=/etc/ssl/ecos/ca-bundle.pem` à `fastapi.env`, puis recréer `api`. Garder le
bundle système : l'import du référentiel télécharge des pages publiques en HTTPS.

### Vérifier

```bash
docker compose -f docker-compose.prod.yml exec api python -c "
import os; from openai import OpenAI
for url, key in [('VLLM_BASE_URL', 'VLLM_API_KEY'), ('VLLM_ARBITER_BASE_URL', 'VLLM_ARBITER_API_KEY')]:
    print(url, [m.id for m in OpenAI(base_url=os.environ[url], api_key=os.environ[key]).models.list()])"
```

Puis, sur le site, lancer une station d'interrogatoire en compte étudiant.

## 4. Exploitation

### Mise à jour

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build   # migrations appliquées par « migrate »
```

L'API refuse de démarrer si `SECRET_KEY` vaut encore la valeur d'exemple (n'importe qui
pourrait fabriquer une session administrateur) : `openssl rand -hex 32`, à coller dans
`fastapi.env`. Changer la clé déconnecte tout le monde, rien d'autre. Un mot de passe
d'exemple dans `DATABASE_URL` donne seulement un avertissement dans les journaux.

### Supervision et journaux

- `GET /health` : `{"status": "ok", "database": true}`, ou 503 si la base est injoignable
  (utilisé par le healthcheck Docker) ;
- `docker compose -f docker-compose.prod.yml logs -f api` ; niveau : `LOG_LEVEL` (INFO) ;
  le contenu des conversations et les mots de passe ne sont jamais journalisés.

### Sauvegardes

```bash
deploy/sauvegarde.sh                          # base (pg_dump) + documents, dans ./sauvegardes/
DOSSIER=/mnt/sauvegardes SAUVEGARDES_A_GARDER=30 deploy/sauvegarde.sh
# cron, chaque nuit :
# 17 2 * * * cd /chemin/ECOS-CHATBOT && deploy/sauvegarde.sh >> sauvegardes/journal.txt 2>&1
```

Copier aussi les sauvegardes hors du serveur. Restauration (écrase la base actuelle) :

```bash
C="docker compose -f docker-compose.prod.yml"
$C exec -T database sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' \
  < sauvegardes/base_AAAA-MM-JJ_HHMM.dump
$C exec -T -u ecos api tar -C /app -xzf - < sauvegardes/documents_AAAA-MM-JJ_HHMM.tar.gz
$C restart api
```

### Durée de conservation (RGPD)

Les tentatives (messages, corrections, signalements) sont gardées jusqu'à leur suppression
par l'étudiant ou par la purge, à planifier avec la durée fixée par le délégué à la protection
des données :

```bash
docker compose -f docker-compose.prod.yml exec -T -u ecos api python scripts/purge_donnees.py --mois 24 --simulation
docker compose -f docker-compose.prod.yml exec -T -u ecos api python scripts/purge_donnees.py --mois 24
```

### Variables utiles (`fastapi.env`)

| Variable | Défaut | Rôle |
|---|---|---|
| `API_WORKERS` (compose) | 2 | processus uvicorn |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` | 10 / 20 / 30 s | connexions par processus ; workers × (taille + débord) < `max_connections` (100) |
| `EVALUATION_TIMEOUT` | 180 | délai d'un appel de correction (s), 3 essais |
| `EVALUATION_SEED` | 1234 | graine de la correction (reproductible) |
| `PATIENT_AGENT_TIMEOUT` | 30 | délai d'une réplique du patient (s) |
| `ARBITER_TIMEOUT` | 2.0 | délai de l'arbitre (s), au-delà le message passe |
| `DOCS_ENABLED` | false | documentation de l'API sur `/docs` (à laisser fermée en production) |
| `LOG_LEVEL` | INFO | niveau des journaux |
| `WEB_BIND` / `WEB_PORT` (compose) | 127.0.0.1 / 8080 | adresse et port publiés du site |

### Licences des modèles

Qwen3-8B (patient, correction) est sous licence Apache 2.0. **Qwen2.5-3B-Instruct
(arbitre) est sous licence de recherche Qwen** : usage non commercial seulement. Pour une
offre payante, le remplacer par un modèle Apache 2.0 (par exemple Qwen2.5-1.5B/7B-Instruct
ou Qwen3-4B, à valider avec `scripts/arbiter_bench.py`).

## Flux réseau à ouvrir

| De | Vers | Port | Usage |
|---|---|---|---|
| navigateurs | serveur de l'application | 443 (reverse proxy) | site, SSE, WebSocket vocal |
| serveur de l'application | machine de modèles | 443 (passerelle) ou 8001, 8002, 8089, 8090 (mode direct) | LLM, voix |
| machine DMZ | huggingface.co, ghcr.io, docker.io, crates.io, pypi.org | 443 | premier démarrage seulement (sinon mode hors ligne) |
