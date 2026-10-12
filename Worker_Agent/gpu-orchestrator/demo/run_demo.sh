#!/bin/bash
# GPU Orchestrator Mini-Project 3: Reproducible Demo
# Owner: Suryansh Bhatnagar
# Usage: ./demo/run_demo.sh [--skip-build] [--help]

set -euo pipefail

# Defaults
SKIP_BUILD=false
HELP=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-build) SKIP_BUILD=true; shift ;;
    --help) HELP=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if $HELP; then
  echo "Usage: ./demo/run_demo.sh [--skip-build]"
  echo "  --skip-build: Skip dependency installation (use if already built)"
  echo "  --help: Show this help"
  exit 0
fi

echo "=== GPU Orchestrator Mini-Project 3 Demo ==="
echo "Owner: Suryansh Bhatnagar"
echo "Timestamp: $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
echo ""

# 1. Environment setup
if ! $SKIP_BUILD; then
  echo "1. Setting up Python virtual environment..."
  python3 -m venv .venv
  source .venv/bin/activate || source .venv/Scripts/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  echo "   ✓ Dependencies installed"
else
  echo "1. Using existing environment (--skip-build)"
  if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
  elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
  fi
fi

# 2. Configuration
export WORKER_ALLOWED_SCRIPT_ROOT="/tmp/demo_scripts"
export SCHEDULER_WORKER_TOKEN="0123456789abcdef0123456789abcdef"  # 32-byte hex
export SCHEDULER_CALLBACK_URL="http://localhost:8002/callback"
export WORKER_ALLOW_NVML_BYPASS=false
mkdir -p "$WORKER_ALLOWED_SCRIPT_ROOT"

# 3. Prepare test scripts
echo "2. Preparing test scripts..."
cat > "$WORKER_ALLOWED_SCRIPT_ROOT/good_script.py" <<'SCRIPT'
print("SUCCESS: Good script completed")
exit(0)
SCRIPT

cat > "$WORKER_ALLOWED_SCRIPT_ROOT/bad_script.py" <<'SCRIPT'
print("ERROR: Bad script failing")
exit(1)
SCRIPT

cat > "$WORKER_ALLOWED_SCRIPT_ROOT/timeout_script.py" <<'SCRIPT'
import time
print("Starting sleep script...")
time.sleep(10)
print("This should not be reached")
exit(0)
SCRIPT

cat > "$WORKER_ALLOWED_SCRIPT_ROOT/env_script.py" <<'SCRIPT'
import os
for k, v in sorted(os.environ.items()):
    print(f"{k}={v}")
exit(0)
SCRIPT

echo "   ✓ Test scripts created in $WORKER_ALLOWED_SCRIPT_ROOT"

# 4. Start launcher
echo "3. Starting Worker Agent on port 8000..."
uvicorn worker-agent.launcher:app --host 0.0.0.0 --port 8000 > demo.log 2>&1 &
LAUNCHER_PID=$!
sleep 3  # Allow startup

# Verify launcher is ready
if ! curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/healthz | grep -q "200"; then
  echo "   ✗ Launcher failed to start! Check demo.log"
  kill $LAUNCHER_PID 2>/dev/null || true
  exit 1
fi
echo "   ✓ Launcher running (PID: $LAUNCHER_PID)"

# 5. Run verification tests
echo "4. Running verification tests..."
TEST_RESULTS=""

# Test 1: Valid dispatch
echo "   ► Test 1: Valid dispatch"
RESPONSE=$(curl -s -X POST http://localhost:8000/dispatch \
  -H "Authorization: Bearer $SCHEDULER_WORKER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"job_id":"demo_valid","script_path":"good_script.py","gpu_indices":[0],"memory_mb":1,"timeout":5}')
if echo "$RESPONSE" | grep -q '"status":"completed"'; then
  TEST_RESULTS="$TEST_RESULTS\n✓ Valid dispatch: PASSED"
else
  TEST_RESULTS="$TEST_RESULTS\n✗ Valid dispatch: FAILED\n$RESPONSE"
fi

# Test 2: Missing script (400)
echo "   ► Test 2: Missing script"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/dispatch \
  -H "Authorization: Bearer $SCHEDULER_WORKER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"job_id":"demo_missing","script_path":"nonexistent.py","gpu_indices":[0],"memory_mb":1,"timeout":5}')
if [ "$RESPONSE" = "400" ]; then
  TEST_RESULTS="$TEST_RESULTS\n✓ Missing script: PASSED (400)"
else
  TEST_RESULTS="$TEST_RESULTS\n✗ Missing script: FAILED (got $RESPONSE)"
fi

# Test 3: Invalid path traversal (400)
echo "   ► Test 3: Path traversal"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/dispatch \
  -H "Authorization: Bearer $SCHEDULER_WORKER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"job_id":"demo_traversal","script_path":"../../etc/passwd.py","gpu_indices":[0],"memory_mb":1,"timeout":5}')
if [ "$RESPONSE" = "400" ]; then
  TEST_RESULTS="$TEST_RESULTS\n✓ Path traversal: PASSED (400)"
else
  TEST_RESULTS="$TEST_RESULTS\n✗ Path traversal: FAILED (got $RESPONSE)"
fi

# Test 4: Non-zero exit (failed)
echo "   ► Test 4: Non-zero exit"
RESPONSE=$(curl -s -X POST http://localhost:8000/dispatch \
  -H "Authorization: Bearer $SCHEDULER_WORKER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"job_id":"demo_fail","script_path":"bad_script.py","gpu_indices":[0],"memory_mb":1,"timeout":5}')
if echo "$RESPONSE" | grep -q '"status":"failed"'; then
  TEST_RESULTS="$TEST_RESULTS\n✓ Non-zero exit: PASSED"
else
  TEST_RESULTS="$TEST_RESULTS\n✗ Non-zero exit: FAILED\n$RESPONSE"
fi

# Test 5: Timeout handling
echo "   ► Test 5: Timeout handling"
RESPONSE=$(curl -s -X POST http://localhost:8000/dispatch \
  -H "Authorization: Bearer $SCHEDULER_WORKER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"job_id":"demo_timeout","script_path":"timeout_script.py","gpu_indices":[0],"memory_mb":1,"timeout":2}')
if echo "$RESPONSE" | grep -q '"status":"timeout"'; then
  TEST_RESULTS="$TEST_RESULTS\n✓ Timeout handling: PASSED"
else
  TEST_RESULTS="$TEST_RESULTS\n✗ Timeout handling: FAILED\n$RESPONSE"
fi

# Test 6: CPU fallback (empty GPU indices)
echo "   ► Test 6: CPU fallback"
RESPONSE=$(curl -s -X POST http://localhost:8000/dispatch \
  -H "Authorization: Bearer $SCHEDULER_WORKER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"job_id":"demo_cpu","script_path":"good_script.py","gpu_indices":[],"memory_mb":1,"timeout":5}')
if echo "$RESPONSE" | grep -q '"status":"completed"'; then
  TEST_RESULTS="$TEST_RESULTS\n✓ CPU fallback: PASSED"
else
  TEST_RESULTS="$TEST_RESULTS\n✗ CPU fallback: FAILED\n$RESPONSE"
fi

# 6. Stop launcher
echo "5. Stopping Worker Agent..."
kill $LAUNCHER_PID 2>/dev/null || true
wait $LAUNCHER_PID 2>/dev/null || true
echo "   ✓ Launcher stopped"

# 7. Report results
echo ""
echo "=== DEMO RESULTS ==="
echo -e "$TEST_RESULTS"
echo ""

# Determine overall success
if echo "$TEST_RESULTS" | grep -q "✗"; then
  echo "✗ DEMO FAILED - See above for details"
  exit 1
else
  echo "✓ DEMO PASSED - All verification tests successful"
  exit 0
fi
