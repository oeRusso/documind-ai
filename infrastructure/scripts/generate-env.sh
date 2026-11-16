#!/usr/bin/env bash
# Create the server's .env with random secrets, WITHOUT printing them (stage 3).
#   infrastructure/scripts/generate-env.sh
# Refuses to overwrite an existing .env. Leaves CLOUDFLARE_TUNNEL_TOKEN empty: Esteban pastes the
# tunnel token himself. Save RESTIC_PASSWORD in your password manager afterwards:
#   grep RESTIC_PASSWORD .env   (only on the server, never in a shared terminal)
set -euo pipefail
cd "$(dirname "$0")/../.."
[[ -e .env ]] && { echo ".env ya existe: no lo piso."; exit 1; }
secret() { head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "${1:-40}"; }
umask 077
cat > .env <<ENV
# DocuMind AI, production. Generated $(date -u +%F). Permissions 600, never committed.
APP_ORIGIN=https://documind.esteban-russo.com
POSTGRES_PASSWORD=$(secret)
APP_DB_PASSWORD=$(secret)
MIGRATOR_DB_PASSWORD=$(secret)
MONITOR_DB_PASSWORD=$(secret)
JWT_SECRET=$(secret 64)
RESTIC_PASSWORD=$(secret 48)
GRAFANA_ADMIN_PASSWORD=$(secret 24)
# Public on purpose (shown on the login page). Empty = no demo.
DEMO_PASSWORD=demo-documind
REGISTRATION_OPEN=false
BACKUP_DIR=$HOME/documind-backups/repo
BACKUP_STAGING=$HOME/documind-backups/staging
BACKUP_OWNER=$(id -u):$(id -g)
# Pasted by Esteban from Cloudflare (Zero Trust > Networks > Tunnels > documind):
CLOUDFLARE_TUNNEL_TOKEN=
ENV
chmod 600 .env
mkdir -p .deploy && echo "-f compose.prod.yaml" > .deploy/compose-files
echo "Listo: .env creado (600) y .deploy/compose-files apunta a compose.prod.yaml."
echo "Falta pegar CLOUDFLARE_TUNNEL_TOKEN en .env y guardar RESTIC_PASSWORD fuera del servidor."
