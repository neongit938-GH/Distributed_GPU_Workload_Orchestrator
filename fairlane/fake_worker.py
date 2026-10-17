"""A pretend Worker Agent for testing. It speaks the real contract but runs no GPU code.
Start one per terminal, e.g.:
  WORKER_NAME=fake-1 PORT=8001 uv run uvicorn fairlane.fake_worker:app --port 8001
"""
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

SERVER = os.getenv("SERVER_URL", "http://127.0.0.1:8000")
NAME = os.getenv("WORKER_NAME", "fake-1")
PORT = int(os.getenv("PORT", "8001"))
GPU_MEM = int(os.getenv("GPU_MEM", "8192"))
JOB_SECONDS = float(os.getenv("FAKE_JOB_SECONDS", "15"))
FAIL_JOB_IDS = {int(x) for x in os.getenv("FAIL_JOB_IDS", "").split(",") if x}   # simulate bad scripts
HEARTBEAT_S = 10

state = {"worker_id": None, "running": set()}
lock = threading.Lock()
stop = threading.Event()


def register():
    r = httpx.post(f"{SERVER}/worker/register", timeout=5, json={
        "worker_name": NAME,
        "agent_url": f"http://127.0.0.1:{PORT}",
        "gpus": [{"gpu_index": 0, "gpu_name": "FakeGPU", "total_memory_mib": GPU_MEM}],
    })
    r.raise_for_status()
    state["worker_id"] = r.json()["worker_id"]
    print(f"[{NAME}] registered as worker {state['worker_id']}", flush=True)


def heartbeat_loop():
    while not stop.wait(HEARTBEAT_S):
        with lock:
            running = sorted(state["running"])
        try:
            r = httpx.post(f"{SERVER}/worker/heartbeat", timeout=5,
                           json={"worker_id": state["worker_id"], "running_execution_ids": running})
            if r.status_code == 409:
                print(f"[{NAME}] server says I was declared offline; registering again", flush=True)
                register()
        except httpx.HTTPError as e:
            print(f"[{NAME}] heartbeat failed: {e}", flush=True)


def run_job(req: "ExecuteRequest"):
    ex = req.execution_id
    with lock:
        state["running"].add(ex)
    try:
        time.sleep(1)                                          # pretend to start a container
        httpx.post(f"{SERVER}/executions/{ex}/started", timeout=5,
                   json={"container_id": f"fake-{uuid.uuid4().hex[:8]}"})
        print(f"[{NAME}] execution {ex} (job {req.job_id}) running for {JOB_SECONDS:.0f}s", flush=True)
        time.sleep(JOB_SECONDS)                                # pretend to train
        code = 1 if req.job_id in FAIL_JOB_IDS else 0
        r = httpx.post(f"{SERVER}/executions/{ex}/complete", timeout=5,
                       json={"exit_code": code, "log_path": f"logs/job_{req.job_id}.log"})
        print(f"[{NAME}] execution {ex} finished with exit {code} -> server: {r.status_code}", flush=True)
    except httpx.HTTPError as e:
        print(f"[{NAME}] callback failed for execution {ex}: {e}", flush=True)
    finally:
        with lock:
            state["running"].discard(ex)


class ExecuteRequest(BaseModel):
    execution_id: int
    job_id: int
    script_path: str
    gpu_index: int
    required_gpu_memory_mib: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    register()
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    yield
    stop.set()


app = FastAPI(title=f"Fake worker {NAME}", lifespan=lifespan)


@app.post("/execute", status_code=202)
def execute(req: ExecuteRequest):
    print(f"[{NAME}] got execution {req.execution_id}: job {req.job_id} ({req.script_path})", flush=True)
    threading.Thread(target=run_job, args=(req,), daemon=True).start()   # reply now, run in background
    return {"accepted": True}














































