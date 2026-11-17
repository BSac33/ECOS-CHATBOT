#!/bin/bash
# Adapté de kyutai-labs/unmute (services/moshi-server/start_moshi_server_public.sh, licence MIT).
set -ex

export LD_LIBRARY_PATH=$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')

uvx hf auth login --token $HUGGING_FACE_HUB_TOKEN

CARGO_TARGET_DIR=/app/target cargo install --features cuda moshi-server@0.6.4

# Chemin complet : le paquet Python "moshi" installe aussi un binaire moshi-server
/root/.cargo/bin/moshi-server $@
