#!/usr/bin/env bash
# Tout-en-un, sans droits administrateur : une commande pour démarrer, une pour arrêter.
#
#   ./modeles.sh demarrer [GPU]   règle .env, installe ce qui manque, lance les LLM puis la voix,
#                                 et affiche la configuration de l'application
#   ./modeles.sh etat             état des modèles
#   ./modeles.sh arreter          arrête tout et libère le GPU
#
# Avec votre Docker personnel (./docker-perso.sh installer) : tout tourne dans Docker, images sur
# la grande partition, GPU par CDI. Sinon : LLM hors Docker (vllm-local.sh), voix dans Docker.
# GPU : numéro de carte (nvidia-smi), retenu dans .env pour les fois suivantes.
# SANS_VOIX=1 ./modeles.sh demarrer : LLM seuls.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

say() { echo "[$(date +%H:%M:%S)] $*"; }
warn() { echo "[$(date +%H:%M:%S)] ATTENTION : $*"; }
die() { echo "Erreur : $*" >&2; exit 1; }
getenv() { sed -n "s/^$1=//p" .env | tail -1; }
setenv() { if grep -q "^$1=" .env; then sed -i "s#^$1=.*#$1=$2#" .env; else echo "$1=$2" >> .env; fi; }
version_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]; }
# Docker personnel (rootless, docker-perso.sh) actif ?
perso() { command -v docker >/dev/null && [ "$(docker context show 2>/dev/null)" = rootless ]; }
MODE=local

configure() {
    command -v nvidia-smi >/dev/null || die "nvidia-smi introuvable : pas de pilote NVIDIA sur cette machine ?"
    [ -f .env ] || { cp .env.example .env; say "Fichier .env créé"; }
    if [ -z "$(getenv MODELS_API_KEY)" ]; then setenv MODELS_API_KEY "$(openssl rand -hex 32)"; say "Clé d'accès générée"; fi
    if [ -z "$(getenv MODELS_BIND)" ]; then
        local ip; ip="$(echo "${SSH_CONNECTION:-}" | awk '{print $3}')"
        [ -n "$ip" ] || die "adresse inconnue : mettez MODELS_BIND=<adresse interne> dans .env (voir hostname -I)"
        setenv MODELS_BIND "$ip"; say "Adresse : $ip"
    fi
    if [ -n "${1:-}" ]; then
        local v; for v in PATIENT_GPU ARBITER_GPU VOICE_GPU; do setenv "$v" "$1"; done
    fi
    # Version CUDA du pilote : l'image vocale ne doit pas être plus récente
    local cuda; cuda="$(nvidia-smi | sed -n 's/.*CUDA Version: *\([0-9.]*\).*/\1/p' | head -1)"
    if version_ge "$cuda" 12.8; then setenv KYUTAI_CUDA_VERSION 12.8.1; else setenv KYUTAI_CUDA_VERSION 12.4.1; fi
    if perso; then
        # Tout dans votre Docker : GPU par CDI, image vLLM adaptée au pilote
        MODE=docker
        setenv COMPOSE_FILE docker-compose.yml:docker-compose.direct.yml:docker-compose.cdi.yml
        if [ "${SANS_VOIX:-0}" = 1 ]; then setenv COMPOSE_PROFILES llm; else setenv COMPOSE_PROFILES llm,voix; fi
        if version_ge "$cuda" 12.8; then setenv VLLM_TAG v0.11.0; else setenv VLLM_TAG v0.8.5.post1; fi
    else
        # LLM hors Docker (vllm-local.sh) : Docker ne lance que la voix
        setenv COMPOSE_FILE docker-compose.yml:docker-compose.direct.yml
        setenv COMPOSE_PROFILES voix
    fi
    set -a; . ./.env; set +a
    say "Pilote CUDA $cuda, GPU ${PATIENT_GPU:-0}, adresse $MODELS_BIND, $( [ $MODE = docker ] && echo 'tout dans votre Docker' || echo 'LLM hors Docker')"
}

check_gpu() {
    local gpu="${PATIENT_GPU:-0}" line free total
    line="$(nvidia-smi --query-gpu=memory.free,memory.total --format=csv,noheader,nounits -i "$gpu" 2>/dev/null)" \
        || die "carte $gpu introuvable (nvidia-smi)"
    free="${line%%,*}"; total="${line##*, }"
    say "Carte $gpu : $((free / 1024)) Go libres sur $((total / 1024)) Go"
    local need; need="$(awk -v t="$total" -v a="${PATIENT_GPU_MEMORY:-0.55}" -v b="${ARBITER_GPU_MEMORY:-0.25}" 'BEGIN{printf "%d", t*(a+b)}')"
    if [ "$free" -lt "$need" ]; then
        warn "il faut environ $((need / 1024)) Go libres pour les LLM : baissez PATIENT_GPU_MEMORY dans .env, ou choisissez une autre carte (./modeles.sh demarrer <numéro>)"
    elif [ "$((free - need))" -lt 8000 ] && [ "${SANS_VOIX:-0}" != 1 ]; then
        warn "il restera moins de 8 Go pour la voix sur cette carte : elle pourrait ne pas démarrer"
    fi
}

start_llm() {
    [ -x data/vllm-local/venv/bin/vllm ] || { say "Installation de vLLM (une seule fois, environ 10 min)"; ./vllm-local.sh install; }
    ./vllm-local.sh start >/dev/null
    say "Chargement des LLM (1re fois : téléchargement d'environ 22 Go, 20 à 60 min)."
    say "Ctrl+C n'arrête pas le chargement : il continue en arrière-plan (./modeles.sh etat)."
    local s start=$SECONDS
    while :; do
        s="$(./vllm-local.sh status)"
        if grep -q "patient : prêt" <<<"$s" && grep -q "arbitre : prêt" <<<"$s"; then break; fi
        if ! grep -q "séquence de démarrage : en cours" <<<"$s"; then
            tail -n 15 data/vllm-local/logs/demarrage.log data/vllm-local/logs/patient.log 2>/dev/null || true
            die "les LLM n'ont pas démarré (journaux ci-dessus : ./vllm-local.sh logs patient)"
        fi
        say "… $(( (SECONDS - start) / 60 )) min : $(grep -o 'patient : [a-zé]*' <<<"$s"), $(grep -o 'arbitre : [a-zé]*' <<<"$s")"
        sleep "${MODELES_POLL:-30}"
    done
    say "LLM prêts."
}

start_voice() {
    if [ "${SANS_VOIX:-0}" = 1 ]; then say "Voix non lancée (SANS_VOIX=1)."; return 1; fi
    command -v docker >/dev/null || { warn "Docker absent : voix non lancée."; return 1; }
    if ! docker image inspect ecos-moshi-server:latest >/dev/null 2>&1; then
        local root avail
        root="$(docker info --format '{{.DockerRootDir}}')"
        avail="$(df -BG --output=avail "$root" | tail -1 | tr -dc 0-9)"
        if [ "$avail" -lt "${VOICE_MIN_FREE_GB:-15}" ]; then
            warn "voix non lancée : l'image vocale demande environ 15 Go sur la partition de Docker ($root), il en reste $avail."
            if docker image inspect vllm/vllm-openai:latest >/dev/null 2>&1 \
               && [ -z "$(docker ps -aq --filter ancestor=vllm/vllm-openai:latest)" ]; then
                echo "    L'image vllm/vllm-openai:latest (~21 Go) n'est utilisée par aucun conteneur. Si elle est à vous :"
                echo "    docker rmi vllm/vllm-openai:latest   puis relancez ./modeles.sh demarrer"
            fi
            return 1
        fi
    fi
    say "Voix : construction et démarrage (1re fois : environ 25 min)."
    docker compose up -d --build
    wait_services stt tts && say "Voix prête."
}

# Attend que les services Docker soient « healthy ». « unhealthy » peut être passager
# (téléchargement, compilation de moshi-server au 1er démarrage) : on n'abandonne que si un
# conteneur s'arrête, ou au bout d'une heure.
wait_services() {
    local svc id state h start=$SECONDS
    for svc in "$@"; do
        while :; do
            id="$(docker compose ps -aq "$svc")"
            state="$( [ -n "$id" ] && docker inspect -f '{{.State.Status}}' "$id" 2>/dev/null || echo absent)"
            h="$( [ -n "$id" ] && docker inspect -f '{{.State.Health.Status}}' "$id" 2>/dev/null || echo absent)"
            [ "$h" = healthy ] && break
            if [ "$state" != running ] || [ $((SECONDS - start)) -gt 3600 ]; then
                docker compose logs --tail 20 "$svc" || true
                warn "$svc n'a pas démarré : docker compose logs $svc"
                return 1
            fi
            say "… $svc en préparation ($(( (SECONDS - start) / 60 )) min)"
            sleep "${MODELES_POLL:-30}"
        done
    done
}

# Tout dans votre Docker personnel (compose attend que le patient soit prêt avant l'arbitre,
# puis l'arbitre avant la voix)
start_docker() {
    say "Démarrage dans votre Docker (1re fois : images, modèles et compilation de la voix, 30 à 90 min)."
    if ! docker compose up -d --build; then
        warn "un service n'est pas encore prêt. Au 1er démarrage, le téléchargement peut dépasser le délai d'attente :"
        echo "    relancez ./modeles.sh demarrer dans quelques minutes (./modeles.sh etat pour suivre)."
        return 1
    fi
    local svcs=(vllm-patient vllm-arbitre); [ "${SANS_VOIX:-0}" = 1 ] || svcs+=(stt tts)
    wait_services "${svcs[@]}" && say "Tout est prêt."
}

print_app_config() {
    cat <<EOF

================ À mettre dans backend_ecos_chatbot/fastapi.env (sur votre poste) ================
VLLM_BASE_URL=http://$MODELS_BIND:${PATIENT_PORT:-8001}/v1
VLLM_ARBITER_BASE_URL=http://$MODELS_BIND:${ARBITER_PORT:-8002}/v1
VLLM_API_KEY=$MODELS_API_KEY
VLLM_ARBITER_API_KEY=$MODELS_API_KEY
KYUTAI_STT_URL=ws://$MODELS_BIND:${STT_PORT:-8090}
KYUTAI_TTS_URL=ws://$MODELS_BIND:${TTS_PORT:-8089}
KYUTAI_API_KEY=$MODELS_API_KEY
===================================================================================================
Puis, sur votre poste : docker compose -f docker-compose.prod.yml up -d --force-recreate api
EOF
}

case "${1:-}" in
    demarrer)
        configure "${2:-}"
        # Mémoire GPU vérifiée seulement si les LLM ne tournent pas déjà (sinon ils l'occupent)
        if [ "$MODE" = docker ]; then
            [ -n "$(docker compose ps -q vllm-patient 2>/dev/null)" ] || check_gpu
            start_docker || true
        else
            if ./vllm-local.sh status | grep -q "patient : arrêté"; then check_gpu; fi
            start_llm
            start_voice || true
        fi
        print_app_config
        ;;
    etat)
        perso || ./vllm-local.sh status
        docker compose ps 2>/dev/null || true
        ;;
    arreter)
        docker compose --profile llm --profile voix down 2>/dev/null || true
        perso || ./vllm-local.sh stop
        say "Tout est arrêté."
        ;;
    *) sed -n '2,13p' "$0"; exit 1 ;;
esac
