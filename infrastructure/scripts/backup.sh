#!/usr/bin/env bash
# Daily encrypted backup (stage 11): database + uploaded documents, with restic.
#   infrastructure/scripts/backup.sh
# Keeps 7 daily and 4 weekly snapshots. Run it from cron / a systemd timer on the server
# (docs/operations/runbook.md); the PC pulls a copy with pull-backups.sh.
source "$(dirname "$0")/lib.sh"

STAGING="${BACKUP_STAGING:-$ROOT/backups/staging}"
REPO="${BACKUP_DIR:-$ROOT/backups/repo}"
mkdir -p "$STAGING" "$REPO"

log "Volcando la base de datos…"
compose exec -T db pg_dump -U postgres -d documind --format=custom > "$STAGING/documind.dump.partial"
mv "$STAGING/documind.dump.partial" "$STAGING/documind.dump"

restic() { compose --profile backup run --rm --no-deps -T backup "$@"; }
if ! restic cat config >/dev/null 2>&1; then
  log "Creando el repositorio cifrado en $REPO"
  restic init
fi
log "Copiando base y documentos…"
restic backup --host documind --tag daily /source/postgres /source/documents
log "Aplicando la retención (7 diarios, 4 semanales)…"
restic forget --host documind --keep-daily 7 --keep-weekly 4 --prune
restic check
rm -f "$STAGING/documind.dump"
log "Backup terminado."
restic snapshots --host documind --compact
