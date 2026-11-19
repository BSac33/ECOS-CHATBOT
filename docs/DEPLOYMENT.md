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
`api` (FastAPI, `API_WORKERS` processus), `web` (nginx : frontend compilé + passerelle vers
l'API). Le site est servi sur `http://<hôte>:${WEB_PORT:-8080}`.

nginx (`frontend/nginx.conf`) sert l'application monopage et relaie :

- `/api/` vers l'API (préfixe retiré) ;
- `/chat/attempts/` sans tampon (flux SSE du patient, WebSocket du mode vocal, 1 h) ;
- `/attachments/` et `/files/` (documents de vignette, ECG, imagerie).

En production, placer un reverse proxy HTTPS devant `web` et mettre `SECURE_COOKIES=True`.
Le micro du navigateur (mode vocal) n'est autorisé qu'en HTTPS ou sur `localhost`.

### Comptes

```bash
docker compose -f docker-compose.prod.yml exec api python scripts/create_user.py admin --role admin
docker compose -f docker-compose.prod.yml exec api python scripts/create_user.py dupont --role teacher --full-name "Dr Dupont"
# sans saisie : -e ECOS_PASSWORD=... ; compte existant : --reset-password
```

### Stations et référentiel

```bash
# Cas d'exemple + packs privés de backend_ecos_chatbot/app/private/stations/ (monté en lecture seule)
# ATTENTION : le seed vide d'abord les cas, tentatives et évaluations (installation initiale seulement)
docker compose -f docker-compose.prod.yml exec api python seed_database.py

# Pack privé ajouté ou mis à jour plus tard, sans rien effacer (idempotent : copier le pack
# dans private/stations/ puis importer tous les packs)
docker compose -f docker-compose.prod.yml exec api python scripts/import_stations.py

# Référentiel officiel de cardiologie (CNEC/SFC) pour l'assistant de rédaction
docker compose -f docker-compose.prod.yml exec api python scripts/ingest_corpus.py
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
KYUTAI_API_KEY=public_token
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

## Flux réseau à ouvrir

| De | Vers | Port | Usage |
|---|---|---|---|
| navigateurs | serveur de l'application | 443 (reverse proxy) | site, SSE, WebSocket vocal |
| serveur de l'application | machine de modèles | 443 (passerelle) ou 8001, 8002, 8089, 8090 (mode direct) | LLM, voix |
| machine DMZ | huggingface.co, ghcr.io, docker.io, crates.io, pypi.org | 443 | premier démarrage seulement (sinon mode hors ligne) |
