#!/bin/bash
# Adapté de kyutai-labs/unmute (services/moshi-server/start_moshi_server_public.sh, licence MIT).
set -e

export LD_LIBRARY_PATH=$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')

# Jeton facultatif : les modèles Kyutai sont publics ; sans jeton (ou hors ligne), pas de connexion
if [ -n "$HUGGING_FACE_HUB_TOKEN" ] && [ "${HF_HUB_OFFLINE:-0}" != "1" ]; then
    uvx hf auth login --token "$HUGGING_FACE_HUB_TOKEN"
fi

# Clé d'accès (KYUTAI_ID, = MODELS_API_KEY de deploy/dmz/.env) : remplace l'identifiant
# d'exemple « public_token » des configs. Le backend l'envoie dans l'en-tête kyutai-api-key
# (KYUTAI_API_KEY de fastapi.env).
if [ -n "${KYUTAI_ID:-}" ]; then
    case "$KYUTAI_ID" in
        *[!A-Za-z0-9._-]*) echo "KYUTAI_ID : lettres, chiffres, . _ - seulement" >&2; exit 1 ;;
    esac
    sed -i "s/^authorized_ids = .*/authorized_ids = [\"$KYUTAI_ID\"]/" configs/*.toml
fi
set -x

# Compilation au premier démarrage seulement : le binaire est rangé dans /app/target (volume),
# les démarrages suivants n'ont besoin ni de crates.io ni du compilateur.
MOSHI_VERSION=0.6.4
MOSHI_ROOT=/app/target/install
if [ "$(cat "$MOSHI_ROOT/.version" 2>/dev/null)" != "$MOSHI_VERSION" ]; then
    CARGO_TARGET_DIR=/app/target cargo install --features cuda --root "$MOSHI_ROOT" "moshi-server@$MOSHI_VERSION"
    echo "$MOSHI_VERSION" > "$MOSHI_ROOT/.version"
fi

# Chemin complet : le paquet Python "moshi" installe aussi un binaire moshi-server
"$MOSHI_ROOT/bin/moshi-server" "$@"
