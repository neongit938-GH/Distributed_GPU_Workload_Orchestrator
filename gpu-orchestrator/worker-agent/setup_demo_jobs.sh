#!/usr/bin/env bash
# Create job scripts at the paths the scheduler's seed jobs use (users/<user>/<job>/train.py).
# bench-c deliberately fails (exit 3) to demonstrate failure reporting.
set -euo pipefail
JOBS_DIR="${JOBS_DIR:-$HOME/fairlane_jobs}"
for p in jack/huge-llm jack/mnist-a jack/bench-c jane/cifar-b jane/cifar-d jane/late-job; do
  mkdir -p "$JOBS_DIR/users/$p"
  printf 'import time\nprint("training %s ...", flush=True)\ntime.sleep(20)\nprint("done")\n' "$p" > "$JOBS_DIR/users/$p/train.py"
done
printf 'import sys\nprint("simulated crash", file=sys.stderr)\nsys.exit(3)\n' > "$JOBS_DIR/users/jack/bench-c/train.py"
echo "Demo job scripts created under $JOBS_DIR/users"
