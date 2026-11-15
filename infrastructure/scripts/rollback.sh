#!/usr/bin/env bash
# Go back to a previous version in seconds: its images are still there (stage 11).
#   infrastructure/scripts/rollback.sh          # the version before the current one
#   infrastructure/scripts/rollback.sh <tag>    # a given one (.deploy/history lists them)
# If that version has fewer migrations, the database is NOT downgraded automatically: the
# script stops and says what to run (a downgrade can lose data of the newer tables).
source "$(dirname "$0")/lib.sh"

CURRENT="$(sed -n 's/^IMAGE_TAG=//p' "$DEPLOY_DIR/image.env")"
TARGET="${1:-$(awk -v cur="$CURRENT" '$4 == cur { prev = $2 } END { print prev }' "$DEPLOY_DIR/history" 2>/dev/null)}"
[[ -n "$TARGET" && "$TARGET" != "$CURRENT" ]] || { echo "No hay versión anterior a $CURRENT"; exit 1; }

started=$SECONDS
head_of() { IMAGE_TAG="$1" compose run --rm --no-deps -T migrate alembic heads 2>/dev/null | awk '{print $1}' | tail -1; }
TARGET_HEAD="$(head_of "$TARGET")"
CURRENT_HEAD="$(head_of "$CURRENT")"
if [[ "$TARGET_HEAD" != "$CURRENT_HEAD" ]]; then
  echo "La versión $TARGET espera la migración $TARGET_HEAD y la base está en $CURRENT_HEAD."
  echo "Bajala primero con la versión actual (puede perder datos de las tablas nuevas):"
  echo "  IMAGE_TAG=$CURRENT ${COMPOSE} run --rm migrate alembic downgrade $TARGET_HEAD"
  exit 1
fi
echo "IMAGE_TAG=$TARGET" > "$DEPLOY_DIR/image.env"
compose up -d --no-build
echo "$(date -u +%FT%TZ) $CURRENT -> $TARGET (rollback)" >> "$DEPLOY_DIR/history"
log "Volviste a $TARGET en $((SECONDS - started)) s."
