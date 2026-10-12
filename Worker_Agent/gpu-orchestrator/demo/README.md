# Fairlane GPU Orchestrator — Mini-Project 3 Demo Package

**Component:** Remote Execution Launcher Verification & Demo Runner  
**Owner:** Suryansh Bhatnagar  
**Project:** Fairlane Distributed ML Scheduling & Orchestration System (Collaborator: Vansh Sagar)  

---

## 🚀 Quick Automated Demonstration

Run the automated 5-stage demonstration script to reproduce all verifications in < 1 minute:

### On Windows PowerShell:
```powershell
# From gpu-orchestrator directory:
powershell -ExecutionPolicy Bypass -File .\demo\run_demo.ps1
```

### On Linux / macOS (Bash):
```bash
# From gpu-orchestrator directory:
chmod +x ./demo/run_demo.sh
./demo/run_demo.sh
```

---

## 📋 What the Automated Demo Validates

The automated demo executes the complete verification sequence across 5 distinct phases:

1. **[1/5] Environment Diagnostic:**  
   Verifies Python 3.12, PyTorch runtime build, and NVML hardware discovery.
2. **[2/5] Standalone Training Script:**  
   Executes `worker-agent/scripts/mnist_cnn.py` to confirm baseline workload reporting, GPU telemetry, and tensor execution.
3. **[3/5] Regression Test Suite (13 Tests):**  
   Executes `pytest worker-agent/tests/test_launcher.py -v` validating health probes, path traversal protection, timeout handling, non-zero exits, NVML resource gating, fail-closed handling, CPU fallback, and job isolation.
4. **[4/5] Live Failure & Resource Pre-Check Scenarios:**  
   Spawns a live worker instance and tests:
   - Missing script rejection (HTTP 400 Bad Request)
   - Simulated script failure (`failing.py` -> `status: failed`, `exit_code: 1`)
   - Hard timeout termination (`timeout.py` with 2s timeout -> `status: timeout`, `exit_code: -9`)
   - NVML pre-dispatch rejection (requesting 9,999,999 MB VRAM -> `status: rejected`)
   - Scheduler contract callback integration (`/dispatch-with-callback` -> `status: completed`, `exit_code: 0`)
5. **[5/5] Evidence File Integrity Check:**  
   Confirms all historic and Phase 8 evidence logs exist in `demo/evidence/` and project root.

---

## 🛠️ Step-by-Step Manual Demo for Live Evaluation

For a structured, live 5–10 minute demonstration for your mentor or team, refer to the full **Live Demonstration Script** in the root [README.md](file:///d:/2_College_and_Career/AStudy/Problem_Based_Learning/PBL_Subjects/5th_Semester_PBL/Worker_Agent/README.md#16-live-demonstration-script-for-mentor-evaluation-510-mins):

1. **Start the Launcher:**  
   ```powershell
   python -m uvicorn worker-agent.launcher:app --host 0.0.0.0 --port 8000
   ```
2. **Probe Liveness:**  
   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8000/healthz" -Method GET
   ```
3. **Dispatch Valid ML Workload:**  
   ```powershell
   $body = '{"job_id":"demo-01","script_path":"sanity_check.py","gpu_indices":[0],"memory_mb":256,"timeout":10}'
   Invoke-RestMethod -Uri "http://localhost:8000/dispatch" -Method POST -Body $body -ContentType "application/json"
   ```
4. **Trigger NVML Memory Rejection:**  
   ```powershell
   $body = '{"job_id":"demo-mem-rej","script_path":"sanity_check.py","gpu_indices":[0],"memory_mb":9999999,"timeout":10}'
   Invoke-RestMethod -Uri "http://localhost:8000/dispatch" -Method POST -Body $body -ContentType "application/json"
   ```
5. **Trigger Security Path Traversal Block:**  
   ```powershell
   $body = '{"job_id":"demo-sec","script_path":"../../secret.py","gpu_indices":[],"memory_mb":0,"timeout":5}'
   Invoke-RestMethod -Uri "http://localhost:8000/dispatch" -Method POST -Body $body -ContentType "application/json"
   ```
6. **Trigger Subprocess Timeout Kill (-9):**  
   ```powershell
   $body = '{"job_id":"demo-timeout","script_path":"timeout.py","gpu_indices":[0],"memory_mb":128,"timeout":2}'
   Invoke-RestMethod -Uri "http://localhost:8000/dispatch" -Method POST -Body $body -ContentType "application/json"
   ```

---

## 📁 Archived Evidence & Artifacts

All test runs, security audits, and contract validations are archived in `demo/evidence/`:

- `phase1_env.txt`: Initial environment baseline dump
- `phase2_script_output.txt`: Neural network baseline execution logs
- `phase3_launcher_test.txt`: Initial launcher test logs
- `phase4_gpu_isolation.txt`: GPU isolation and NVML telemetry logs
- `phase5_concurrent_jobs.txt`: Concurrency and parallel isolation logs
- `phase6_failure_contract.txt`: Failure injection and callback validation logs
- `phase6_contract_agreement.txt`: Vansh Sagar interface agreement confirmation
- `phase8_gpu_audit.txt`: Final GPU detection audit across execution modes
- `phase8_regression_tests.txt`: Final 13-test regression suite output
- `phase8_security_review.txt`: Path traversal, authentication, and bypass security audit
- `phase8_contract_validation.txt`: Full schema audit against Vansh Sagar's scheduler interface
- `phase8_final_report.txt`: Final handover report

---

## ⚠️ Hardware & Scope Notice

- **GPU Telemetry vs PyTorch Wheel:** The host machine is equipped with an NVIDIA GeForce RTX 2050 (4GB VRAM). The Worker Agent directly queries physical GPU telemetry (free memory, utilization) via `pynvml`. Workload scripts run under the installed CPU PyTorch wheel (`torch==2.14.1+cpu`) in this testbed; the Worker Agent is fully framework-agnostic and isolates GPUs via `CUDA_VISIBLE_DEVICES`.
- **Single-Node Testbed:** Validation was performed locally on a single host as documented in `remote_limitation.txt`. The Worker Agent is network-ready and binds to `0.0.0.0` for multi-node deployments.
