#!/usr/bin/env bash
# Shared by the operation scripts (stage 11). Sourced, not run.
# COMPOSE: "podman compose" on the PC, "docker compose" on the VPS (detected if not set).
# The image tag of the running version lives in .deploy/image.env (IMAGE_TAG=<git commit>),
# passed with --env-file next to .env, so every command uses the same images.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
DEPLOY_DIR="$ROOT/.deploy"
mkdir -p "$DEPLOY_DIR"
[[ -f "$DEPLOY_DIR/image.env" ]] || echo "IMAGE_TAG=dev" > "$DEPLOY_DIR/image.env"

if [[ -z "${COMPOSE:-}" ]]; then
  # Podman first: the PC may also have an (empty) Docker; the VPS has only Docker.
  if command -v podman >/dev/null 2>&1; then
    COMPOSE="podman compose"
  else
    COMPOSE="docker compose"
  fi
fi
# shellcheck disable=SC2206  # word splitting wanted: "docker compose" is two words
COMPOSE_CMD=($COMPOSE --env-file .env --env-file "$DEPLOY_DIR/image.env" ${COMPOSE_FILES:-})

compose() { "${COMPOSE_CMD[@]}" "$@"; }
log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
