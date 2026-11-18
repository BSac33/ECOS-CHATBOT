# Serveur de modèles (DMZ)

Les modèles tournent sur une machine GPU de la DMZ ; l'application (site, API, base) tourne
ailleurs et les appelle à travers une seule passerelle HTTPS.

```
serveur de l'application  ──HTTPS / WSS──▶  passerelle nginx (:443)  ──réseau Docker interne──▶  vllm-patient  (Qwen3-8B)
  (APP_SERVER_CIDR)            clé d'API       liste d'IP, TLS                                    vllm-arbitre  (Qwen2.5-3B)
                                                                                                  stt, tts      (Kyutai, profil « voix »)
```

Seul le port de la passerelle est publié. Les modèles ne sont pas joignables directement.

## Prérequis

- Linux, pilote NVIDIA, Docker avec le plugin Compose (≥ 2.20) et le NVIDIA Container Toolkit
- Une L40S 48 Go (ou équivalent) suffit pour l'ensemble ; ~60 Go de disque pour `./data`
- Un certificat pour le nom DNS de la machine (PKI de l'IHU de préférence)
- Pare-feu : n'ouvrir le port HTTPS qu'au serveur de l'application

## Installation

```bash
cd deploy/dmz
cp .env.example .env
openssl rand -hex 32            # -> MODELS_API_KEY dans .env
# APP_SERVER_CIDR = adresse du serveur de l'application, ex. 10.20.30.40/32

mkdir -p certs
cp /chemin/vers/fullchain.pem /chemin/vers/privkey.pem certs/
# Sans PKI (tests uniquement), certificat autosigné :
#   openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=modeles.ihu.local" \
#     -addext "subjectAltName=DNS:modeles.ihu.local" -keyout certs/privkey.pem -out certs/fullchain.pem

docker compose up -d --build
docker compose ps
```

Le premier démarrage est long : environ 16 Go de poids pour le modèle patient, 6 Go pour
l'arbitre et ~8 Go pour la voix. moshi-server se compile aussi au premier lancement (~10 min).
Les services démarrent les uns après les autres (patient, puis arbitre, puis voix), parce que
chaque serveur vLLM mesure la mémoire GPU libre au lancement.

Vérifications depuis le serveur de l'application :

```bash
curl https://modeles.ihu.local/healthz                                   # ok
curl -H "Authorization: Bearer $CLE" https://modeles.ihu.local/patient/v1/models
curl -H "Authorization: Bearer $CLE" https://modeles.ihu.local/arbitre/v1/models
```

## Côté application (`backend_ecos_chatbot/fastapi.env`)

```bash
VLLM_BASE_URL=https://modeles.ihu.local/patient/v1
VLLM_MODEL=Qwen/Qwen3-8B
VLLM_API_KEY=<MODELS_API_KEY>
VLLM_ARBITER_BASE_URL=https://modeles.ihu.local/arbitre/v1
VLLM_ARBITER_MODEL=Qwen/Qwen2.5-3B-Instruct
VLLM_ARBITER_API_KEY=<MODELS_API_KEY>
KYUTAI_STT_URL=wss://modeles.ihu.local/stt
KYUTAI_TTS_URL=wss://modeles.ihu.local/tts
KYUTAI_API_KEY=<MODELS_API_KEY>
# Certificat de la PKI interne : AC à ajouter au magasin du conteneur (voir docs/DEPLOYMENT.md)
SSL_CERT_FILE=/etc/ssl/ecos/ca-bundle.pem
```

L'assistant de rédaction (`AUTHORING_*`) utilise le modèle patient quand ses variables sont vides.

## Routes de la passerelle

| Chemin | Service | Authentification |
|---|---|---|
| `/patient/v1/...` | vLLM patient (API OpenAI, flux SSE) | `Authorization: Bearer <clé>` |
| `/arbitre/v1/...` | vLLM arbitre | `Authorization: Bearer <clé>` |
| `/stt/api/asr-streaming` | Kyutai STT (WebSocket) | `kyutai-api-key: <clé>` |
| `/tts/api/tts_streaming` | Kyutai TTS (WebSocket) | `kyutai-api-key: <clé>` |
| `/healthz` | passerelle | aucune (liste d'IP seulement) |

La passerelle remplace la clé Kyutai par l'identifiant interne de moshi-server ; la clé des
LLM est relayée et vérifiée aussi par vLLM. Les réponses en flux ne sont pas mises en tampon,
les WebSocket restent ouverts jusqu'à 1 h. nginx ne journalise ni les corps ni les en-têtes :
les transcriptions des étudiants n'apparaissent pas dans les journaux.

## Variantes

- **Sans voix** : `COMPOSE_PROFILES=` dans `.env`. La passerelle répond 502 sur `/stt` et `/tts`.
- **Deux GPU** : `PATIENT_GPU=0`, `ARBITER_GPU=1`, `VOICE_GPU=1`, `PATIENT_GPU_MEMORY=0.85`.
- **Plusieurs adresses autorisées** : ajouter des lignes `allow` dans
  `gateway/default.conf.template` (avant `deny all`).
- **Reverse proxy TLS déjà en place à l'IHU** : le faire pointer sur la passerelle et mettre
  son adresse dans `APP_SERVER_CIDR`.

## Sans accès sortant (DMZ fermée)

Après un premier démarrage réussi sur une machine connectée, `./data` contient tout ce
qu'il faut : poids (`hf-cache`), binaire moshi-server compilé (`kyutai/*-target/install`) et
paquets Python (`kyutai/uv-cache`). Copier le dossier `deploy/dmz` complet et les images
(`docker save vllm/vllm-openai:<tag> nginx:<tag> ecos-moshi-server:latest | gzip > modeles.tar.gz`,
puis `docker load` sur la DMZ), mettre `OFFLINE=1` dans `.env`, puis `docker compose up -d`
(sans `--build`).

## Mise à jour

```bash
docker compose pull && docker compose up -d     # nouvelle version de vLLM : VLLM_TAG dans .env
```

Les noms de modèles (`PATIENT_MODEL`, `ARBITER_MODEL`) doivent rester identiques à
`VLLM_MODEL` / `VLLM_ARBITER_MODEL` côté application.
