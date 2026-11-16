#!/usr/bin/env bash
# Restore database and documents from a backup (stage 11).
#   infrastructure/scripts/restore.sh            # the latest snapshot
#   infrastructure/scripts/restore.sh <id>       # one snapshot (restic snapshots lists them)
# It REPLACES the current data: the API and the worker are stopped meanwhile.
source "$(dirname "$0")/lib.sh"

SNAPSHOT="${1:-latest}"
STAGING="${BACKUP_STAGING:-$ROOT/backups/staging}"
mkdir -p "$STAGING" "${BACKUP_DIR:-$ROOT/backups/repo}"
restic() { compose --profile backup run --rm --no-deps -T backup "$@"; }

log "Deteniendo la API y el worker…"
compose stop api worker web >/dev/null
log "Restaurando la copia $SNAPSHOT…"
# SELinux labels belong to the machine, not to the data: never restored.
restic restore "$SNAPSHOT" --target / --include /source/postgres --exclude-xattr "security.*"
# --delete: files uploaded after the backup are removed, so files and database match.
restic restore "$SNAPSHOT" --target / --include /source/documents --delete \
  --exclude-xattr "security.*"
log "Cargando la base de datos…"
compose exec -T db pg_restore -U postgres -d documind --clean --if-exists --exit-on-error \
  < "$STAGING/documind.dump"
rm -f "$STAGING/documind.dump"
log "Levantando todo…"
compose up -d --no-build api worker web >/dev/null
log "Restauración terminada."
