"""Fairlane Worker Agent: connects launcher.py to the central scheduler.

launcher.py does the work (path checks, NVML pre-check, subprocess, timeout, log tails).
This file adds what the scheduler needs:
  - POST /worker/register on startup, then a heartbeat every 10 s
  - POST /execute  -> validate, reply 202 at once, run the job in a background thread
  - POST /executions/{id}/started and /complete back to the scheduler

Run (from the worker-agent folder):
  SERVER_URL=http://<scheduler-ip>:8000 AGENT_URL=http://<this-machine-ip>:8001 \
  WORKER_ALLOWED_SCRIPT_ROOT=/mnt/shared_jobs  python -m uvicorn agent:app --host 0.0.0.0 --port 8001
"""
import logging
import os
import socket
import threading
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import launcher  # reuse every check and the process runner

log = logging.getLogger("worker-agent")

SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:8000")
WORKER_NAME = os.getenv("WORKER_NAME", socket.gethostname())
AGENT_URL = os.getenv("AGENT_URL", "http://127.0.0.1:8001")    # how the SCHEDULER reaches this agent
JOB_TIMEOUT_S = int(os.getenv("JOB_TIMEOUT_S", "3600"))        # scheduler sends no timeout yet
USE_GPU = os.getenv("WORKER_USE_GPU", "true").lower() == "true"
FALLBACK_GPU_MEM_MIB = int(os.getenv("WORKER_FAKE_GPU_MEM_MIB", "4096"))  # used when NVML can't see a GPU
HEARTBEAT_S = 10

state = {"worker_id": None, "running": set()}
lock = threading.Lock()
stop = threading.Event()


def discover_gpus() -> list[dict]:
    """Ask NVML which GPUs exist. Without NVML (e.g. a VM), report one placeholder GPU."""
    if USE_GPU and launcher.NVML_AVAILABLE:
        try:
            launcher.pynvml.nvmlInit()
            gpus = []
            for i in range(launcher.pynvml.nvmlDeviceGetCount()):
                h = launcher.pynvml.nvmlDeviceGetHandleByIndex(i)
                name = launcher.pynvml.nvmlDeviceGetName(h)
                name = name.decode() if isinstance(name, bytes) else name
                total = launcher.pynvml.nvmlDeviceGetMemoryInfo(h).total // (1024 * 1024)
                gpus.append({"gpu_index": i, "gpu_name": name, "total_memory_mib": int(total)})
            launcher.pynvml.nvmlShutdown()
            if gpus:
                return gpus
        except Exception as e:
            log.warning(f"NVML discovery failed ({e}); reporting a placeholder GPU")
    return [{"gpu_index": 0, "gpu_name": "no-gpu (CPU execution)", "total_memory_mib": FALLBACK_GPU_MEM_MIB}]


def register():
    r = httpx.post(f"{SERVER_URL}/worker/register", timeout=10, json={
        "worker_name": WORKER_NAME, "agent_url": AGENT_URL, "gpus": discover_gpus()})
    r.raise_for_status()
    state["worker_id"] = r.json()["worker_id"]
    log.info(f"registered with {SERVER_URL} as worker {state['worker_id']} ({WORKER_NAME})")


def heartbeat_loop():
    while not stop.wait(HEARTBEAT_S):
        with lock:
            running = sorted(state["running"])
        try:
            r = httpx.post(f"{SERVER_URL}/worker/heartbeat", timeout=5,
                           json={"worker_id": state["worker_id"], "running_execution_ids": running})
            if r.status_code == 409:      # server declared us dead; our old jobs were requeued
                log.warning("scheduler says this worker was declared offline; registering again")
                register()
        except httpx.HTTPError as e:
            log.warning(f"heartbeat failed: {e}")


class ExecuteRequest(BaseModel):
    """Exactly what the scheduler's dispatch.py sends."""
    execution_id: int
    job_id: int
    script_path: str               # relative to WORKER_ALLOWED_SCRIPT_ROOT (the NFS mount)
    gpu_index: int
    required_gpu_memory_mib: int


def run_and_report(req: ExecuteRequest, script: str, gpu_indices: list[int]):
    ex = req.execution_id
    with lock:
        state["running"].add(ex)
    try:
        httpx.post(f"{SERVER_URL}/executions/{ex}/started", timeout=10,
                   json={"container_id": f"proc-exec{ex}"})
        result = launcher.run_process_job(f"exec{ex}", script, gpu_indices, JOB_TIMEOUT_S)
        log_path = os.path.join(launcher.DEFAULT_LOG_DIR, f"job_exec{ex}.out")
        r = httpx.post(f"{SERVER_URL}/executions/{ex}/complete", timeout=10,
                       json={"exit_code": result.exit_code, "log_path": log_path})
        log.info(f"execution {ex}: {result.status} (exit {result.exit_code}) -> scheduler HTTP {r.status_code}")
    except Exception as e:
        log.error(f"execution {ex}: reporting failed: {e}")
    finally:
        with lock:
            state["running"].discard(ex)


@asynccontextmanager
async def lifespan(app: FastAPI):
    register()
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="Fairlane Worker Agent", lifespan=lifespan)
app.include_router(launcher.app.router)          # keeps /healthz, /dispatch, /dispatch-with-callback


@app.post("/execute", status_code=202)
def execute(req: ExecuteRequest):
    gpu_indices = [req.gpu_index] if USE_GPU else []
    # Reuse launcher's validation: raises HTTP 400 for bad paths -> scheduler requeues the job
    check = launcher.DispatchRequest(job_id=str(req.job_id), script_path=req.script_path,
                                     gpu_indices=gpu_indices, timeout=JOB_TIMEOUT_S,
                                     memory_mb=req.required_gpu_memory_mib)
    script = launcher.validate_dispatch_request(check)
    reason = launcher.check_gpu_resources(gpu_indices, req.required_gpu_memory_mib)
    if reason:
        raise HTTPException(status_code=409, detail=reason)   # NVML says no -> scheduler requeues
    threading.Thread(target=run_and_report, args=(req, script, gpu_indices), daemon=True).start()
    return {"accepted": True, "execution_id": req.execution_id}
