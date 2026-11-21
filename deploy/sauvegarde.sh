#!/usr/bin/env bash
# Sauvegarde de l'application (base PostgreSQL + documents téléversés), à lancer depuis la
# racine du dépôt, sur le serveur de l'application. Garde les SAUVEGARDES_A_GARDER dernières.
#
#   deploy/sauvegarde.sh                       # dans ./sauvegardes/
#   DOSSIER=/mnt/sauvegardes deploy/sauvegarde.sh
#   cron (chaque nuit à 2 h 17) :
#   17 2 * * * cd /chemin/ECOS-CHATBOT && deploy/sauvegarde.sh >> sauvegardes/journal.txt 2>&1
#
# Restauration : voir docs/DEPLOYMENT.md (section « Sauvegardes »). Copiez aussi les
# sauvegardes HORS de ce serveur (autre machine, stockage de l'établissement).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

COMPOSE="docker compose -f docker-compose.prod.yml"
DOSSIER="${DOSSIER:-$PWD/sauvegardes}"
GARDER="${SAUVEGARDES_A_GARDER:-14}"
date="$(date +%Y-%m-%d_%H%M)"
mkdir -p "$DOSSIER"

# Base : format personnalisé (pg_restore), cohérent même pendant l'utilisation
$COMPOSE exec -T database sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$DOSSIER/base_$date.dump"
# Documents téléversés (volume api_storage, monté sur /app/storage)
$COMPOSE exec -T api tar -C /app -czf - storage > "$DOSSIER/documents_$date.tar.gz"

for prefix in base documents; do
    ls -1t "$DOSSIER"/${prefix}_* 2>/dev/null | tail -n +"$((GARDER + 1))" | xargs -r rm -f
done
echo "[$(date '+%F %T')] Sauvegarde : $DOSSIER/base_$date.dump ($(du -h "$DOSSIER/base_$date.dump" | cut -f1)), documents_$date.tar.gz"
