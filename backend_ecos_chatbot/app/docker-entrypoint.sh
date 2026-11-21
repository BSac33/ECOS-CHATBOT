#!/bin/sh
# Démarre en root uniquement pour rendre /app/storage (volume des pièces jointes : ancienne
# image en root, scripts lancés par « docker compose exec ») à l'utilisateur « ecos », puis
# abandonne les privilèges.
set -e
if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/storage
    find /app/storage ! -user ecos -exec chown ecos:ecos {} +
    exec setpriv --reuid=ecos --regid=ecos --init-groups "$@"
fi
exec "$@"
