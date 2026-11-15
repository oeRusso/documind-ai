#!/usr/bin/env bash
# Deploy the current commit (stage 11; built on the server, no registry: ADR 0013).
#   infrastructure/scripts/deploy.sh            # git pull --ff-only, build, migrate, start
#   infrastructure/scripts/deploy.sh --no-pull  # deploy what is checked out (local test)
# Images are tagged with the commit, so the previous ones stay for rollback.sh.
source "$(dirname "$0")/lib.sh"

[[ "${1:-}" == "--no-pull" ]] || git pull --ff-only
TAG="$(git rev-parse --short=12 HEAD)"
PREVIOUS="$(sed -n 's/^IMAGE_TAG=//p' "$DEPLOY_DIR/image.env")"

log "Construyendo las imágenes $TAG…"
IMAGE_TAG="$TAG" compose build api worker web
echo "IMAGE_TAG=$TAG" > "$DEPLOY_DIR/image.env"
log "Migrando y levantando…"
compose up -d --no-build
echo "$(date -u +%FT%TZ) $PREVIOUS -> $TAG" >> "$DEPLOY_DIR/history"
log "Versión $TAG en marcha (anterior: $PREVIOUS)."
