#!/usr/bin/env bash
# Run on YOUR PC: copy the encrypted backup repository off the server (stage 11, no cloud).
#   infrastructure/scripts/pull-backups.sh usuario@servidor [/srv/documind-backups/repo] [destino]
# The copy is encrypted (restic): it is useless without RESTIC_PASSWORD, which you keep apart.
set -euo pipefail
SERVER="${1:?usage: pull-backups.sh user@server [remote repo] [local dir]}"
REMOTE="${2:-/srv/documind-backups/repo}"
LOCAL="${3:-$HOME/documind-backups/repo}"
mkdir -p "$LOCAL"
rsync -a --delete --info=stats1 "$SERVER:$REMOTE/" "$LOCAL/"
echo "Copia actualizada en $LOCAL"
