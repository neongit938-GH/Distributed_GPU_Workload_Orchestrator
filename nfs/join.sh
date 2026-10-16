#!/usr/bin/env bash
# Join THIS machine to Fairlane shared storage.
# Usage: sudo bash nfs/join.sh SERVER_IP_OR_HOSTNAME [--persist]
#   --persist  also add the mount to /etc/fstab (only on a stable network)
# Before running: the server's /etc/exports must allow this machine's network.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/registry.conf"
[[ $EUID -eq 0 ]] || { echo "Run with sudo"; exit 1; }
SERVER=${1:?usage: sudo bash nfs/join.sh SERVER_IP_OR_HOSTNAME [--persist]}

echo "== 1. NFS client"
command -v mount.nfs4 >/dev/null || { apt-get update -q; apt-get install -y -q nfs-common; }

echo "== 2. Accounts"
bash "$DIR/sync_accounts.sh"

echo "== 3. Mount"
mkdir -p "$MOUNT_POINT"
if findmnt -n "$MOUNT_POINT" >/dev/null; then
  echo "already mounted"
else
  mount -t nfs4 "$SERVER:$SERVER_EXPORT" "$MOUNT_POINT"
fi

if [[ ${2:-} == --persist ]]; then
  if grep -q "[[:space:]]$MOUNT_POINT[[:space:]]" /etc/fstab; then
    echo "fstab entry already present"
  else
    echo "$SERVER:$SERVER_EXPORT $MOUNT_POINT nfs4 defaults,_netdev,nofail 0 0" >> /etc/fstab
    echo "added fstab entry"
  fi
fi

echo "== 4. Verify"
bash "$DIR/verify.sh"
