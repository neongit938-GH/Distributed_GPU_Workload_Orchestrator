import asyncio
import json
import os
import subprocess
import time
import httpx


async def run_safe_concurrent_test():
    print("=== STARTING PHASE 5 TEST 1: SAFE CONCURRENT EXECUTION ===")
    ts = int(time.time())
    job_a_id = f"concurrent_safe_a_{ts}"
    job_b_id = f"concurrent_safe_b_{ts}"

    # Start GPU monitor
    monitor_log_path = "gpu_monitor_concurrent_safe.log"
    monitor_file = open(monitor_log_path, "w", encoding="utf-8")
    monitor_proc = subprocess.Popen(
        ["nvidia-smi", "dmon", "-s", "u", "-i", "0", "-c", "20"],
        stdout=monitor_file,
        stderr=subprocess.STDOUT,
    )
    print(f"Started GPU monitor (PID {monitor_proc.pid}) -> {monitor_log_path}")

    async def dispatch(job_id: str, delay_before: float = 0.0):
        if delay_before > 0:
            print(f"Waiting {delay_before}s before dispatching {job_id}...")
            await asyncio.sleep(delay_before)

        payload = {
            "job_id": job_id,
            "script_path": "memory_workload.py",
            "gpu_indices": [0],
            "timeout": 30,
            "args": ["--mem-fraction", "0.1", "--duration", "10"],
        }
        print(f"Dispatching {job_id} at T+{time.time()-ts:.2f}s...")
        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post("http://127.0.0.1:8000/dispatch", json=payload)
            print(f"Received response for {job_id} at T+{time.time()-ts:.2f}s")
            return resp.json()

    # Launch Job A immediately, and Job B after 3 seconds
    task_a = asyncio.create_task(dispatch(job_a_id, delay_before=0.0))
    task_b = asyncio.create_task(dispatch(job_b_id, delay_before=3.0))

    res_a, res_b = await asyncio.gather(task_a, task_b)

    # Clean up monitor
    try:
        monitor_proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        monitor_proc.kill()
    monitor_file.close()

    print("\n--- JOB A RESPONSE ---")
    print(json.dumps(res_a, indent=2))

    print("\n--- JOB B RESPONSE ---")
    print(json.dumps(res_b, indent=2))

    with open(monitor_log_path, "r", encoding="utf-8", errors="replace") as f:
        mon_content = f.read()
    print("\n--- GPU MONITOR LOG ---")
    print(mon_content)

    return res_a, res_b, mon_content


if __name__ == "__main__":
    asyncio.run(run_safe_concurrent_test())
