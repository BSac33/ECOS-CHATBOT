# Serveur de modèles (DMZ)

Les modèles tournent sur une machine GPU ; l'application (site, API, base) tourne ailleurs
(serveur web, ou poste local relié par VPN) et les appelle par le réseau.

| Service | Modèle | Rôle |
|---|---|---|
| `vllm-patient` | Qwen/Qwen3-8B (vLLM, outils Hermes) | patient simulé, évaluation, assistant de rédaction |
| `vllm-arbitre` | Qwen/Qwen2.5-3B-Instruct (vLLM) | filtre rapide des messages étudiants |
| `stt`, `tts` | Kyutai moshi-server (profil `voix`) | mode vocal |
| `gateway` | nginx (profil `passerelle`) | facultatif : HTTPS + clé + liste d'IP |

Trois façons d'y accéder :

1. **Test par VPN** (mode direct) : ports publiés sur l'adresse interne de la machine, clé
   vLLM, sans TLS ni nginx. C'est la configuration par défaut de `.env.example`.
2. **Derrière un nginx déjà en place** : mode direct sur `127.0.0.1`, le nginx existant relaie.
3. **Passerelle fournie** : nginx en conteneur, HTTPS, seul port publié.

## Prérequis

- Linux, pilote NVIDIA, Docker avec le plugin Compose (≥ 2.20), NVIDIA Container Toolkit
- Version de vLLM selon le pilote (`nvidia-smi`, « CUDA Version ») : 12.8 ou plus → `VLLM_TAG=v0.11.0`
  (défaut) ; 12.4 → `VLLM_TAG=v0.8.5.post1` (Qwen3 et outils pris en charge)
- GPU : ~38 Go pour les deux LLM (L40S 48 Go), ~8 Go de plus pour la voix
- ~60 Go de disque pour `./data` (ou un cache Hugging Face existant via `HF_CACHE_DIR`)

## 1. Test par VPN (mode direct)

```bash
git clone https://github.com/BSac33/ECOS-CHATBOT.git && cd ECOS-CHATBOT/deploy/dmz
cp .env.example .env
nvidia-smi          # machine partagée : choisir un GPU et des fractions qui tiennent dans la mémoire libre
hostname -I         # adresse interne, celle que vous joignez par le VPN
```

Dans `.env` :

- `MODELS_API_KEY` : `openssl rand -hex 32`
- `MODELS_BIND` : l'adresse interne (jamais `0.0.0.0` sur une machine de DMZ)
- `PATIENT_GPU`, `ARBITER_GPU`, `PATIENT_GPU_MEMORY`, `ARBITER_GPU_MEMORY` selon `nvidia-smi`
- ports (`PATIENT_PORT`…) si 8001/8002 sont déjà pris par d'autres
- `COMPOSE_PROFILES=llm,voix` pour le mode vocal (par défaut `llm` : LLM seuls)

```bash
docker compose up -d --build
docker compose ps                       # attendre « healthy » (premier démarrage : 20 à 60 min)
docker compose logs -f vllm-patient     # suivre le téléchargement et le chargement
```

Depuis votre poste (VPN connecté) :

```bash
curl -H "Authorization: Bearer <clé>" http://<adresse>:8001/v1/models
curl -H "Authorization: Bearer <clé>" http://<adresse>:8002/v1/models
```

Côté application (`backend_ecos_chatbot/fastapi.env`) :

```bash
VLLM_BASE_URL=http://<adresse>:8001/v1
VLLM_API_KEY=<clé>
VLLM_ARBITER_BASE_URL=http://<adresse>:8002/v1
VLLM_ARBITER_API_KEY=<clé>
KYUTAI_STT_URL=ws://<adresse>:8090
KYUTAI_TTS_URL=ws://<adresse>:8089
KYUTAI_API_KEY=public_token
```

Limites du mode direct : trafic en clair (il reste dans le VPN), voix protégée par
l'identifiant par défaut de moshi-server (`public_token`). À réserver aux tests, sans données
réelles d'étudiants.

## 1 bis. Partition de Docker trop petite : LLM hors Docker

Docker range ses images sur sa propre partition (`docker info --format '{{.DockerRootDir}}'`),
souvent la partition système, et ce réglage demande des droits administrateur. Si elle manque
de place, les LLM peuvent tourner sans Docker, installés dans le projet (donc sur la partition
du projet), avec `vllm-local.sh` ; Docker ne sert plus qu'à la voix (image ~10 Go).

```bash
./vllm-local.sh install     # une fois : uv, Python, vLLM dans data/vllm-local (~10 Go)
./vllm-local.sh start       # patient puis arbitre, en arrière-plan (survit à la déconnexion)
./vllm-local.sh status      # « prêt » quand les modèles répondent
./vllm-local.sh logs        # journal du patient (logs arbitre, logs demarrage)
./vllm-local.sh stop        # arrête tout et libère le GPU
```

Le script lit le même `.env` (clé, `MODELS_BIND`, ports, GPU, fractions de mémoire) ; les
adresses vues par l'application sont identiques à celles de la version Docker. La version de
vLLM suit le pilote (`nvidia-smi`, « CUDA Version ») : 12.8 ou plus → 0.11.0, sinon
0.8.5.post1 (forçable avec `VLLM_PIP_VERSION`). La clé passe par l'environnement, jamais en
argument (visible par tous avec `ps` sur une machine partagée).

Voix dans Docker en même temps : retirer `llm` des profils, et compiler l'image vocale pour la
version CUDA du pilote :

```bash
# .env : COMPOSE_PROFILES=voix   KYUTAI_CUDA_VERSION=12.4.1 (pilote en CUDA 12.4)
./vllm-local.sh start                          # d'abord les LLM (mémoire GPU)
docker compose up -d --build                   # puis la voix ; 1er démarrage : compilation ~10 min
docker compose logs -f stt                     # « healthy » quand moshi-server répond
```

## 2. Derrière un nginx déjà en place (production)

Si le nginx est sur la même machine : mode direct avec `MODELS_BIND=127.0.0.1` (rien n'est
publié sur le réseau), puis reprendre dans sa configuration les blocs `location` de
`gateway/default.conf.template` et les réglages de `gateway/snippets/` en remplaçant les
upstreams par `127.0.0.1:<port>` :

- vLLM : `proxy_buffering off` (réponses en flux), `proxy_read_timeout 600s`, en-tête
  `Authorization` relayé (vLLM vérifie la clé) ;
- Kyutai : WebSocket (`Upgrade`/`Connection`), `proxy_read_timeout 3600s`, contrôle de
  `kyutai-api-key` puis remplacement par `public_token` ;
- filtrage `allow`/`deny` sur l'adresse du serveur de l'application.

Si le nginx est sur une autre machine : `MODELS_BIND` = adresse interne, et un pare-feu qui
n'autorise que l'adresse de ce nginx.

## 3. Passerelle fournie (nginx en conteneur)

Dans `.env` : commenter `COMPOSE_FILE` et `MODELS_BIND`, `COMPOSE_PROFILES=passerelle` (ou
`voix,passerelle`), `APP_SERVER_CIDR` = adresse du serveur de l'application. Certificats :

```bash
mkdir -p certs && cp /chemin/fullchain.pem /chemin/privkey.pem certs/
# sans PKI (tests) : certificat autosigné pour l'adresse IP
#   openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=ecos-modeles" \
#     -addext "subjectAltName=IP:<adresse>" -keyout certs/privkey.pem -out certs/fullchain.pem
docker compose up -d --build
```

| Chemin | Service | Authentification |
|---|---|---|
| `/patient/v1/...` | vLLM patient (flux SSE) | `Authorization: Bearer <clé>` |
| `/arbitre/v1/...` | vLLM arbitre | `Authorization: Bearer <clé>` |
| `/stt/api/asr-streaming` | Kyutai STT (WebSocket) | `kyutai-api-key: <clé>` |
| `/tts/api/tts_streaming` | Kyutai TTS (WebSocket) | `kyutai-api-key: <clé>` |
| `/healthz` | passerelle | aucune (liste d'IP seulement) |

Côté application : `https://<hôte>/patient/v1`, `https://<hôte>/arbitre/v1`,
`wss://<hôte>/stt`, `wss://<hôte>/tts`, la même clé partout (y compris `KYUTAI_API_KEY`).
Certificat d'une AC interne ou autosigné : `SSL_CERT_FILE` (docs/DEPLOYMENT.md).

## Démarrage, mémoire GPU

Les services démarrent les uns après les autres (patient, puis arbitre, puis voix) : chaque
vLLM vérifie au lancement que la fraction demandée de la mémoire **totale** du GPU est libre.
Sur une machine partagée, si un vLLM refuse de démarrer faute de mémoire, baisser
`PATIENT_GPU_MEMORY` / `ARBITER_GPU_MEMORY` (et `PATIENT_MAX_MODEL_LEN`) ou changer de GPU.

## Sans accès sortant

Après un premier démarrage réussi sur une machine connectée, `./data` contient tout :
poids (`hf-cache`), binaire moshi-server compilé (`kyutai/*-target/install`), paquets Python
(`kyutai/uv-cache`). Copier le dossier `deploy/dmz` et les images
(`docker save vllm/vllm-openai:<tag> nginx:<tag> ecos-moshi-server:latest | gzip > modeles.tar.gz`,
puis `docker load`), mettre `OFFLINE=1` dans `.env`, puis `docker compose up -d` (sans `--build`).

## Mise à jour, arrêt

```bash
docker compose pull && docker compose up -d     # nouvelle version de vLLM : VLLM_TAG dans .env
                                                # (télécharge ~20 Go sur la partition de Docker)
docker compose down                             # libère le GPU (les poids restent dans ./data)
```

Les noms de modèles (`PATIENT_MODEL`, `ARBITER_MODEL`) doivent rester identiques à
`VLLM_MODEL` / `VLLM_ARBITER_MODEL` côté application.
