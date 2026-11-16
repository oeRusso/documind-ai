#!/usr/bin/env bash
# Daily encrypted backup (stage 11): database + uploaded documents, with restic.
#   infrastructure/scripts/backup.sh
# Keeps 7 daily and 4 weekly snapshots. Run it from cron / a systemd timer on the server
# (docs/operations/runbook.md); the PC pulls a copy with pull-backups.sh.
source "$(dirname "$0")/lib.sh"

# Same paths that compose mounts: the caller's environment first, then .env, then ./backups.
env_value() { sed -n "s/^$1=//p" "$ROOT/.env" 2>/dev/null | tail -1; }
STAGING="${BACKUP_STAGING:-$(env_value BACKUP_STAGING)}"
REPO="${BACKUP_DIR:-$(env_value BACKUP_DIR)}"
OWNER="${BACKUP_OWNER:-$(env_value BACKUP_OWNER)}"
export BACKUP_STAGING="${STAGING:-$ROOT/backups/staging}" BACKUP_DIR="${REPO:-$ROOT/backups/repo}"
STAGING="$BACKUP_STAGING"
REPO="$BACKUP_DIR"
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
if [[ -n "$OWNER" ]]; then
  # With Docker the restic container writes as root; give the repository back to the deploy
  # user so pull-backups.sh (rsync over SSH) can read it. Podman rootless does not need it.
  compose --profile backup run --rm --no-deps -T --entrypoint chown backup -R "$OWNER" /repo
fi
log "Backup terminado."
restic snapshots --host documind --compact
