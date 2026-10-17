import asyncio
import json
import os
import subprocess
import time
import httpx


async def run_contention_test():
    print("=== STARTING PHASE 5 TEST 2: MEMORY CONTENTION TEST ===")
    ts = int(time.time())
    job_c_id = f"contention_high_{ts}"
    job_d_id = f"contention_mnist_{ts}"

    # Start GPU monitor
    monitor_log_path = "gpu_monitor_contention.log"
    monitor_file = open(monitor_log_path, "w", encoding="utf-8")
    monitor_proc = subprocess.Popen(
        ["nvidia-smi", "dmon", "-s", "u", "-i", "0", "-c", "25"],
        stdout=monitor_file,
        stderr=subprocess.STDOUT,
    )
    print(f"Started GPU monitor (PID {monitor_proc.pid}) -> {monitor_log_path}")

    async def dispatch_c():
        payload = {
            "job_id": job_c_id,
            "script_path": "memory_workload.py",
            "gpu_indices": [0],
            "timeout": 30,
            "args": ["--mem-fraction", "0.6", "--duration", "10"],
        }
        print(f"Dispatching Job C ({job_c_id}) at T+{time.time()-ts:.2f}s...")
        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post("http://127.0.0.1:8000/dispatch", json=payload)
            print(f"Received response for Job C at T+{time.time()-ts:.2f}s")
            return resp.json()

    async def dispatch_d():
        print("Waiting 3.0s before dispatching Job D...")
        await asyncio.sleep(3.0)
        payload = {
            "job_id": job_d_id,
            "script_path": "mnist_cnn.py",
            "gpu_indices": [0],
            "timeout": 30,
            "args": ["--synthetic", "--epochs", "1"],
        }
        print(f"Dispatching Job D ({job_d_id}) at T+{time.time()-ts:.2f}s...")
        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post("http://127.0.0.1:8000/dispatch", json=payload)
            print(f"Received response for Job D at T+{time.time()-ts:.2f}s")
            return resp.json()

    task_c = asyncio.create_task(dispatch_c())
    task_d = asyncio.create_task(dispatch_d())

    res_c, res_d = await asyncio.gather(task_c, task_d)

    # Clean up monitor
    try:
        monitor_proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        monitor_proc.kill()
    monitor_file.close()

    print("\n--- JOB C (HIGH MEMORY) RESPONSE ---")
    print(json.dumps(res_c, indent=2))

    print("\n--- JOB D (MNIST WORKLOAD) RESPONSE ---")
    print(json.dumps(res_d, indent=2))

    with open(monitor_log_path, "r", encoding="utf-8", errors="replace") as f:
        mon_content = f.read()
    print("\n--- GPU MONITOR LOG ---")
    print(mon_content)

    return res_c, res_d, mon_content


if __name__ == "__main__":
    asyncio.run(run_contention_test())
