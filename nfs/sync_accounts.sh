#!/usr/bin/env bash
# Create Fairlane accounts with the fixed IDs from registry.conf.
# Safe to re-run: existing correct accounts are left alone.
# Stops with an error if a name or number is already used differently.
# Usage: sudo bash nfs/sync_accounts.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/registry.conf"
[[ $EUID -eq 0 ]] || { echo "Run with sudo"; exit 1; }

ensure_group() {
  local name=$1 gid=$2
  if getent group "$name" >/dev/null; then
    local have; have=$(getent group "$name" | cut -d: -f3)
    [[ $have == "$gid" ]] || { echo "ERROR: group $name has GID $have, registry says $gid"; exit 1; }
  elif getent group "$gid" >/dev/null; then
    echo "ERROR: GID $gid is already used by group $(getent group "$gid" | cut -d: -f1)"; exit 1
  else
    groupadd -g "$gid" "$name"; echo "created group $name ($gid)"
  fi
}

ensure_user() {
  local name=$1 uid=$2 group=$3
  if id "$name" &>/dev/null; then
    local have; have=$(id -u "$name")
    [[ $have == "$uid" ]] || { echo "ERROR: user $name has UID $have, registry says $uid"; exit 1; }
  elif getent passwd "$uid" >/dev/null; then
    echo "ERROR: UID $uid is already used by user $(getent passwd "$uid" | cut -d: -f1)"; exit 1
  else
    useradd -m -u "$uid" -g "$group" -s /bin/bash "$name"; echo "created user $name ($uid)"
  fi
}

ensure_group "$WORKER_GROUP" "$WORKER_ID"
ensure_user  "$WORKER_USER"  "$WORKER_ID" "$WORKER_GROUP"

for entry in $USERS; do
  name=${entry%%:*}; uid=${entry##*:}
  ensure_group "$name" "$uid"
  ensure_user  "$name" "$uid" "$name"
done

echo "OK: accounts on $(hostname) match the registry"
