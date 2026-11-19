#!/usr/bin/env bash
# vLLM SANS Docker, installé dans le dossier du projet, sans droits administrateur.
# Pour une machine où la partition de Docker manque de place : les LLM tournent ici,
# Docker ne sert plus qu'à la voix. Même configuration que docker-compose : le fichier .env.
#
#   ./vllm-local.sh install   # une fois : Python + vLLM dans data/vllm-local (~10 Go)
#   ./vllm-local.sh start     # lance le patient, puis l'arbitre quand le patient est prêt
#   ./vllm-local.sh status    # état des deux serveurs
#   ./vllm-local.sh logs [patient|arbitre|demarrage]   # suit un journal (Ctrl+C pour quitter)
#   ./vllm-local.sh stop      # arrête les deux serveurs (libère le GPU)
#
# Variables de .env utilisées : MODELS_API_KEY, MODELS_BIND, PATIENT_PORT, ARBITER_PORT,
# PATIENT_GPU, ARBITER_GPU, PATIENT_GPU_MEMORY, ARBITER_GPU_MEMORY, PATIENT_MODEL,
# ARBITER_MODEL, PATIENT_MAX_MODEL_LEN ; facultatives : VLLM_PIP_VERSION (sinon choisie
# d'après le pilote : CUDA >= 12.8 -> 0.11.0, sinon 0.8.5.post1), VLLM_LOCAL_DIR.
# La clé passe par l'environnement (VLLM_API_KEY), jamais en argument : sur une machine
# partagée, les arguments des processus sont visibles par tous (ps).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELF="$HERE/$(basename "${BASH_SOURCE[0]}")"
if [ ! -f "$HERE/.env" ]; then
    echo "Fichier $HERE/.env absent : cp .env.example .env, puis le remplir." >&2
    exit 1
fi
set -a; . "$HERE/.env"; set +a

DIR="${VLLM_LOCAL_DIR:-$HERE/data/vllm-local}"
case "$DIR" in /*) ;; *) DIR="$HERE/$DIR" ;; esac
VENV="$DIR/venv"; LOGS="$DIR/logs"; RUN="$DIR/run"
# Tous les caches et fichiers temporaires dans DIR (pas dans le dossier personnel ni /tmp)
export UV_CACHE_DIR="$DIR/uv-cache" UV_PYTHON_INSTALL_DIR="$DIR/python" TMPDIR="$DIR/tmp" \
       XDG_CACHE_HOME="$DIR/cache" HF_HOME="$DIR/hf-cache" HF_HUB_OFFLINE="${OFFLINE:-0}"

PATIENT_PORT="${PATIENT_PORT:-8001}"; ARBITER_PORT="${ARBITER_PORT:-8002}"
PATIENT_GPU="${PATIENT_GPU:-0}"; ARBITER_GPU="${ARBITER_GPU:-0}"
PATIENT_GPU_MEMORY="${PATIENT_GPU_MEMORY:-0.55}"; ARBITER_GPU_MEMORY="${ARBITER_GPU_MEMORY:-0.25}"
PATIENT_MODEL="${PATIENT_MODEL:-Qwen/Qwen3-8B}"; ARBITER_MODEL="${ARBITER_MODEL:-Qwen/Qwen2.5-3B-Instruct}"
PATIENT_MAX_MODEL_LEN="${PATIENT_MAX_MODEL_LEN:-32768}"
START_TIMEOUT="${VLLM_START_TIMEOUT:-3600}"   # premier démarrage : téléchargement des poids

say() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "Erreur : $*" >&2; exit 1; }
version_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]; }   # $1 >= $2
driver_cuda() { nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: *\([0-9.]*\).*/\1/p' | head -1; }
running() { [ -f "$RUN/$1.pid" ] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null; }
healthy() { curl -sf -o /dev/null --max-time 5 "http://$MODELS_BIND:$1/health"; }

check_config() {
    [ -n "${MODELS_API_KEY:-}" ] || die "MODELS_API_KEY est vide dans .env"
    [ -n "${MODELS_BIND:-}" ] || die "MODELS_BIND est vide dans .env (adresse interne de la machine)"
    [ "$MODELS_BIND" != "0.0.0.0" ] || die "MODELS_BIND=0.0.0.0 exposerait les modèles sur toutes les interfaces"
}

cmd_install() {
    local version="${VLLM_PIP_VERSION:-}"
    if [ -z "$version" ]; then
        local cuda; cuda="$(driver_cuda)"
        [ -n "$cuda" ] || die "nvidia-smi ne répond pas : pilote NVIDIA absent ?"
        if version_ge "$cuda" 12.8; then version=0.11.0; else version=0.8.5.post1; fi
        say "Pilote NVIDIA : CUDA $cuda -> vLLM $version"
    fi
    mkdir -p "$DIR/bin" "$TMPDIR" "$LOGS" "$RUN"
    local uv="$DIR/bin/uv"
    if [ ! -x "$uv" ]; then
        say "Installation de uv dans $DIR/bin"
        curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$DIR/bin" UV_NO_MODIFY_PATH=1 sh
    fi
    [ -x "$VENV/bin/python" ] || "$uv" venv --python 3.12 "$VENV"
    say "Installation de vLLM $version (plusieurs Go, quelques minutes)"
    "$uv" pip install --python "$VENV/bin/python" "vllm==$version"
    echo "$version" > "$DIR/vllm-version"
    say "Installé : $("$VENV/bin/python" -c 'import vllm; print("vLLM", vllm.__version__)')"
}

serve() {   # nom port gpu fraction modèle [options...]
    local name=$1 port=$2 gpu=$3 mem=$4 model=$5; shift 5
    local extra=()
    # Avant 0.10.2, vLLM écrit les messages reçus dans son journal : désactivé
    version_ge "$(cat "$DIR/vllm-version")" 0.10.2 || extra+=(--disable-log-requests)
    say "Démarrage $name : $model sur $MODELS_BIND:$port (GPU $gpu, $mem de la mémoire)"
    # setsid : vLLM et ses processus enfants forment un groupe à part, arrêté d'un bloc par « stop »
    CUDA_VISIBLE_DEVICES="$gpu" VLLM_API_KEY="$MODELS_API_KEY" setsid nohup "$VENV/bin/vllm" serve "$model" \
        --host "$MODELS_BIND" --port "$port" --gpu-memory-utilization "$mem" \
        --enable-prefix-caching ${extra[@]+"${extra[@]}"} "$@" > "$LOGS/$name.log" 2>&1 &
    echo $! > "$RUN/$name.pid"
}

wait_healthy() {   # nom port
    local waited=0
    until healthy "$2"; do
        running "$1" || die "$1 s'est arrêté : voir $LOGS/$1.log"
        [ "$waited" -lt "$START_TIMEOUT" ] || die "$1 pas prêt après ${START_TIMEOUT}s : voir $LOGS/$1.log"
        sleep 5; waited=$((waited + 5))
    done
    say "$1 prêt (http://$MODELS_BIND:$2/v1)"
}

# Lancé en arrière-plan par « start » : patient, puis arbitre une fois le patient prêt
# (chaque vLLM vérifie au démarrage que sa part de mémoire GPU est libre).
cmd_sequence() {
    if ! running patient; then
        serve patient "$PATIENT_PORT" "$PATIENT_GPU" "$PATIENT_GPU_MEMORY" "$PATIENT_MODEL" \
            --dtype bfloat16 --max-model-len "$PATIENT_MAX_MODEL_LEN" \
            --enable-auto-tool-choice --tool-call-parser hermes
    fi
    wait_healthy patient "$PATIENT_PORT"
    if ! running arbitre; then
        serve arbitre "$ARBITER_PORT" "$ARBITER_GPU" "$ARBITER_GPU_MEMORY" "$ARBITER_MODEL" \
            --dtype float16 --max-model-len 8192
    fi
    wait_healthy arbitre "$ARBITER_PORT"
    say "Les deux modèles sont prêts."
}

cmd_start() {
    check_config
    [ -x "$VENV/bin/vllm" ] && [ -f "$DIR/vllm-version" ] || die "vLLM n'est pas installé : $SELF install"
    mkdir -p "$LOGS" "$RUN" "$TMPDIR"
    if running sequence; then say "Démarrage déjà en cours (logs demarrage)"; return; fi
    nohup "$SELF" _sequence > "$LOGS/demarrage.log" 2>&1 &
    echo $! > "$RUN/sequence.pid"
    say "Démarrage lancé en arrière-plan. Suivre : $SELF logs demarrage   (ou logs patient)"
    say "Premier démarrage : téléchargement des poids (~22 Go) puis chargement, 20 à 60 min."
}

cmd_status() {
    local name port
    for name in patient arbitre; do
        [ "$name" = patient ] && port=$PATIENT_PORT || port=$ARBITER_PORT
        if running "$name"; then
            if healthy "$port"; then echo "$name : prêt      http://$MODELS_BIND:$port/v1"
            else echo "$name : démarrage (voir : $0 logs $name)"; fi
        else echo "$name : arrêté"; fi
    done
    running sequence && echo "séquence de démarrage : en cours" || true
}

cmd_stop() {
    local name pid target
    for name in sequence arbitre patient; do
        if running "$name"; then
            pid="$(cat "$RUN/$name.pid")"
            # vLLM : tout le groupe (processus enfants compris) ; séquence : le processus seul
            if [ "$name" = sequence ]; then target="$pid"; else target="-$pid"; fi
            kill -TERM -- "$target" 2>/dev/null || true
            for _ in $(seq 30); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
            kill -KILL -- "$target" 2>/dev/null || true
            say "$name arrêté"
        fi
        rm -f "$RUN/$name.pid"
    done
}

cmd_logs() {
    local f="$LOGS/${1:-patient}.log"
    [ -f "$f" ] || die "pas de journal $f"
    tail -n 50 -f "$f"
}

case "${1:-}" in
    install) cmd_install ;;
    start) cmd_start ;;
    _sequence) check_config; cmd_sequence ;;
    status) cmd_status ;;
    stop) cmd_stop ;;
    logs) cmd_logs "${2:-patient}" ;;
    *) sed -n '2,11p' "$0"; exit 1 ;;
esac
