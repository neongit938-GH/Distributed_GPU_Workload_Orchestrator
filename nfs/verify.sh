#!/usr/bin/env bash
# Check that this machine sees the share with the right permissions.
# Usage: sudo bash nfs/verify.sh
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/registry.conf"
[[ $EUID -eq 0 ]] || { echo "Run with sudo"; exit 1; }

fails=0
pass() { echo "  PASS  $1"; }
fail() { echo "  FAIL  $1"; fails=$((fails + 1)); }

read -r -a list <<< "$USERS"
u1=${list[0]%%:*}

findmnt -n "$MOUNT_POINT" >/dev/null && pass "share mounted at $MOUNT_POINT" || { fail "share not mounted"; exit 1; }

sudo -u "$WORKER_USER" ls "$MOUNT_POINT/users/$u1" >/dev/null 2>&1 \
  && pass "worker can read users/$u1" || fail "worker cannot read users/$u1"

probe="$MOUNT_POINT/logs/$u1/.fl_probe"
sudo -u "$WORKER_USER" sh -c "echo ok > '$probe' && rm '$probe'" 2>/dev/null \
  && pass "worker can write logs/$u1" || fail "worker cannot write logs/$u1"

if sudo -u "$WORKER_USER" touch "$MOUNT_POINT/users/$u1/.fl_probe" 2>/dev/null; then
  fail "worker could WRITE into users/$u1 (should be read-only)"
else
  pass "worker cannot write users/$u1"
fi

if [[ ${#list[@]} -ge 2 ]]; then
  u2=${list[1]%%:*}
  if sudo -u "$u2" ls "$MOUNT_POINT/users/$u1" >/dev/null 2>&1; then
    fail "$u2 can read $u1's folder (isolation broken)"
  else
    pass "$u2 cannot read $u1's folder"
  fi
fi

[[ $fails -eq 0 ]] && echo "ALL CHECKS PASSED" || { echo "$fails CHECK(S) FAILED"; exit 1; }
