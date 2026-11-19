#!/usr/bin/env bash
# Docker personnel (mode « rootless »), sans droits administrateur, images rangées sur une
# grande partition au lieu de la partition système. Accès au GPU par CDI.
#
#   ./docker-perso.sh installer      une fois : installe, démarre et active votre Docker
#   ./docker-perso.sh tester         vérifie le stockage et l'accès au GPU
#   ./docker-perso.sh etat           état de votre Docker
#   ./docker-perso.sh desinstaller   revient au Docker de la machine (les images restent)
#
# Une fois installé, toutes vos commandes docker utilisent votre Docker (contexte « rootless ») ;
# celui de la machine reste accessible avec : docker --context default …
# Images : DOCKER_PERSO_DATA, par défaut le dossier docker-perso à côté du projet.
# Prérequis (vérifiés) : plages /etc/subuid et /etc/subgid pour votre compte, paquets
# docker-ce-rootless-extras et nvidia-container-toolkit.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

DATA_ROOT="${DOCKER_PERSO_DATA:-$(cd ../../.. && pwd)/docker-perso}"
CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
CONF="$CONF_DIR/docker/daemon.json"
CDI_DIR="$CONF_DIR/cdi"

say() { echo "[$(date +%H:%M:%S)] $*"; }
warn() { echo "[$(date +%H:%M:%S)] ATTENTION : $*"; }
die() { echo "Erreur : $*" >&2; exit 1; }
gpu() { sed -n 's/^PATIENT_GPU=//p' .env 2>/dev/null | tail -1 | grep . || echo 0; }

cmd_installer() {
    local u; u="$(id -un)"
    grep -q "^$u:" /etc/subuid && grep -q "^$u:" /etc/subgid \
        || die "pas de plages /etc/subuid et /etc/subgid pour $u : à demander à l'administrateur"
    local c; for c in dockerd-rootless-setuptool.sh rootlesskit newuidmap nvidia-ctk python3; do
        command -v "$c" >/dev/null || die "$c introuvable"
    done
    mkdir -p "$DATA_ROOT" "$CDI_DIR" "$(dirname "$CONF")"
    say "Images de votre Docker : $DATA_ROOT ($(df -h --output=avail "$DATA_ROOT" | tail -1 | tr -d ' ') libres)"

    say "Description des GPU pour Docker (CDI) : $CDI_DIR/nvidia.yaml"
    nvidia-ctk cdi generate --output="$CDI_DIR/nvidia.yaml" >/dev/null 2>"$CDI_DIR/generate.log" \
        || { cat "$CDI_DIR/generate.log"; die "nvidia-ctk cdi generate a échoué"; }
    say "GPU décrits : $(sed -n 's/^ *- name: *"\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' "$CDI_DIR/nvidia.yaml" | tr '\n' ' ')"

    # Configuration de votre Docker : stockage + CDI (réglages existants conservés)
    python3 - "$CONF" "$DATA_ROOT" "$CDI_DIR" <<'EOF'
import json, os, sys
path, root, cdi = sys.argv[1:]
conf = json.load(open(path)) if os.path.exists(path) and os.path.getsize(path) else {}
conf["data-root"] = root
conf.setdefault("features", {})["cdi"] = True
dirs = conf.get("cdi-spec-dirs") or ["/etc/cdi", "/var/run/cdi"]
if cdi not in dirs:
    dirs.append(cdi)
conf["cdi-spec-dirs"] = dirs
with open(path, "w") as f:
    json.dump(conf, f, indent=2)
EOF
    say "Configuration : $CONF"

    if systemctl --user cat docker.service >/dev/null 2>&1; then
        say "Redémarrage de votre Docker"
        systemctl --user restart docker
    else
        say "Installation de votre Docker (rootless)"
        local opts=(--force)   # --force : le Docker de la machine tourne à côté, c'est voulu
        command -v iptables >/dev/null || opts+=(--skip-iptables)
        dockerd-rootless-setuptool.sh install "${opts[@]}"
    fi

    # Garder votre Docker allumé après la déconnexion
    if loginctl enable-linger "$(id -un)" 2>/dev/null; then
        say "Votre Docker restera allumé après la déconnexion."
    else
        warn "impossible d'activer « linger » : votre Docker s'arrêtera quand vous fermerez toutes vos sessions."
        echo "    Solution : demander à l'administrateur « loginctl enable-linger $(id -un) », ou garder une session ouverte (tmux)."
    fi

    docker context use rootless >/dev/null
    say "Vos commandes docker utilisent maintenant votre Docker (contexte rootless)."
    cmd_tester
}

cmd_tester() {
    local root g
    root="$(docker --context rootless info --format '{{.DockerRootDir}}' 2>/dev/null)" \
        || die "votre Docker ne répond pas : systemctl --user status docker ; journalctl --user -u docker | tail -30"
    say "Stockage : $root ($(df -h --output=avail "$root" | tail -1 | tr -d ' ') libres)"
    g="$(gpu)"
    say "Test du GPU $g dans un conteneur (télécharge ubuntu:22.04, ~80 Mo, la 1re fois)"
    if docker --context rootless run --rm --device "nvidia.com/gpu=$g" ubuntu:22.04 nvidia-smi -L; then
        say "Votre Docker voit le GPU : ./modeles.sh demarrer $g lancera tout dans Docker."
    else
        warn "le conteneur ne voit pas le GPU. Envoyez la sortie ci-dessus ; en attendant, ./docker-perso.sh desinstaller"
        echo "    puis ./modeles.sh demarrer $g (LLM hors Docker)."
        return 1
    fi
}

cmd_etat() {
    echo "contexte docker actif : $(docker context show)"
    echo "service : $(systemctl --user is-active docker 2>&1)"
    docker --context rootless info --format 'stockage : {{.DockerRootDir}}' 2>/dev/null || echo "votre Docker ne répond pas"
}

cmd_desinstaller() {
    docker context use default >/dev/null 2>&1 || true
    dockerd-rootless-setuptool.sh uninstall || true
    say "Retour au Docker de la machine. Vos images restent dans $DATA_ROOT."
    echo "    Pour les supprimer : rootlesskit rm -rf $DATA_ROOT   (rm seul ne suffit pas)"
}

case "${1:-}" in
    installer) cmd_installer ;;
    tester) cmd_tester ;;
    etat) cmd_etat ;;
    desinstaller) cmd_desinstaller ;;
    *) sed -n '2,15p' "$0"; exit 1 ;;
esac
