import httpx
from sqlalchemy import func, select

from fairlane.db import SessionLocal
from fairlane.failure import requeue_worker_jobs
from fairlane.models import Job, JobExecution, Worker, WorkerGPU

DISPATCH_TIMEOUT_S = 3


def dispatch(execution_id: int) -> bool:
    """Send one ASSIGNED execution to its worker. Returns True if the worker accepted it."""
    # 1. Read what to send (short transaction, no locks held during the network call)
    with SessionLocal() as session:
        ex, job, worker, gpu = session.execute(
            select(JobExecution, Job, Worker, WorkerGPU)
            .join(Job, Job.job_id == JobExecution.job_id)
            .join(Worker, Worker.worker_id == JobExecution.worker_id)
            .join(WorkerGPU, WorkerGPU.gpu_id == JobExecution.gpu_id)
            .where(JobExecution.execution_id == execution_id)
        ).one()
        url = f"{worker.agent_url}/execute"
        worker_id = worker.worker_id
        payload = {
            "execution_id": ex.execution_id,
            "job_id": job.job_id,
            "script_path": job.script_path,
            "gpu_index": gpu.gpu_index,
            "required_gpu_memory_mib": job.required_gpu_memory,
        }

    # 2. Call the worker
    try:
        response = httpx.post(url, json=payload, timeout=DISPATCH_TIMEOUT_S)
        if response.status_code == 202:
            return True
        reason, worker_down = f"dispatch rejected: HTTP {response.status_code}", False
    except httpx.HTTPError as e:
        reason, worker_down = f"dispatch failed: {type(e).__name__}", True

    # 3. Undo the assignment so the job can be scheduled again
    with SessionLocal() as session, session.begin():
        if worker_down:
            # Unreachable worker: take it out of rotation and requeue everything it held
            session.get(Worker, worker_id, with_for_update=True).status = "OFFLINE"
            requeue_worker_jobs(session, worker_id, reason)
        else:
            ex = session.get(JobExecution, execution_id, with_for_update=True)
            if ex.status == "ASSIGNED":
                ex.status, ex.failure_reason, ex.ended_at = "FAILED", reason, func.now()
                session.get(Job, ex.job_id, with_for_update=True).status = "QUEUED"
    return False





























