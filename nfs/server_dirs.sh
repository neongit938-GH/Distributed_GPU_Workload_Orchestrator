#!/usr/bin/env bash
# SERVER ONLY. Create/repair each user's folders with the correct owner and mode.
#   users/<u> : owner <u>, group compute_workers, 750  (user rw, workers read)
#   logs/<u>  : owner fl_worker, group <u>, 750        (worker writes, user reads)
# Usage: sudo bash nfs/server_dirs.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/registry.conf"
[[ $EUID -eq 0 ]] || { echo "Run with sudo"; exit 1; }

bash "$DIR/sync_accounts.sh"

for entry in $USERS; do
  name=${entry%%:*}
  mkdir -p "$SERVER_EXPORT/users/$name" "$SERVER_EXPORT/logs/$name"
  chown "$name:$WORKER_GROUP"       "$SERVER_EXPORT/users/$name"
  chown "$WORKER_USER:$name"        "$SERVER_EXPORT/logs/$name"
  chmod 750 "$SERVER_EXPORT/users/$name" "$SERVER_EXPORT/logs/$name"
  echo "folders ready for $name"
done

ls -ln "$SERVER_EXPORT/users" "$SERVER_EXPORT/logs"
