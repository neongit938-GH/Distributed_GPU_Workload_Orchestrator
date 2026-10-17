#!/usr/bin/env bash
# Start the Fairlane Worker Agent (agent.py) on Linux.
# Usage:  SERVER_URL=http://<scheduler-ip>:8000 AGENT_URL=http://<this-ip>:8001 ./run_agent.sh
# Optional: WORKER_NAME, WORKER_USE_GPU (default false), WORKER_FAKE_GPU_MEM_MIB, JOBS_DIR, PORT
set -euo pipefail
cd "$(dirname "$0")"
[ -f .venv/bin/activate ] && source .venv/bin/activate
: "${SERVER_URL:?set SERVER_URL, e.g. http://10.190.94.174:8000}"
: "${AGENT_URL:?set AGENT_URL to this machine IP, e.g. http://10.190.94.171:8001}"
PORT="${PORT:-8001}"
export SERVER_URL AGENT_URL
export WORKER_NAME="${WORKER_NAME:-$(hostname)}"
export WORKER_USE_GPU="${WORKER_USE_GPU:-false}"
export WORKER_FAKE_GPU_MEM_MIB="${WORKER_FAKE_GPU_MEM_MIB:-12000}"
export WORKER_ALLOWED_SCRIPT_ROOT="${JOBS_DIR:-$HOME/fairlane_jobs}"
echo "Agent '$WORKER_NAME' -> scheduler $SERVER_URL, reachable at $AGENT_URL, scripts in $WORKER_ALLOWED_SCRIPT_ROOT"
exec python -m uvicorn agent:app --host 0.0.0.0 --port "$PORT"
