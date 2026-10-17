from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fairlane.db import SessionLocal
from fairlane.failure import ACTIVE, requeue_worker_jobs
from fairlane.models import Job, JobExecution, Worker, WorkerGPU

router = APIRouter()


def get_session():
    with SessionLocal() as session:
        yield session


# ---------- request bodies (Pydantic validates them automatically) ----------

class GPUInfo(BaseModel):
    gpu_index: int = Field(ge=0)
    gpu_name: str | None = None
    total_memory_mib: int = Field(gt=0)


class RegisterRequest(BaseModel):
    worker_name: str
    agent_url: str
    gpus: list[GPUInfo] = Field(min_length=1)


class HeartbeatRequest(BaseModel):
    worker_id: int
    running_execution_ids: list[int] = []


class StartedRequest(BaseModel):
    container_id: str


class CompleteRequest(BaseModel):
    exit_code: int
    log_path: str | None = None


# ---------- endpoints ----------

@router.post("/worker/register")
def register(req: RegisterRequest, session: Session = Depends(get_session)):
    with session.begin():
        worker = session.scalars(
            select(Worker).where(Worker.worker_name == req.worker_name).with_for_update()
        ).first()
        requeued = []
        if worker is None:
            worker = Worker(worker_name=req.worker_name, agent_url=req.agent_url)
            session.add(worker)
            session.flush()
        else:
            # A worker that registers again has restarted: whatever it was running is gone.
            requeued = requeue_worker_jobs(session, worker.worker_id, "worker restarted")
        worker.agent_url = req.agent_url
        if worker.status != "DRAINING":
            worker.status = "ONLINE"
        worker.last_heartbeat = func.now()

        existing = {g.gpu_index: g for g in session.scalars(
            select(WorkerGPU).where(WorkerGPU.worker_id == worker.worker_id))}
        for g in req.gpus:
            row = existing.get(g.gpu_index)
            if row is None:
                session.add(WorkerGPU(worker_id=worker.worker_id, gpu_index=g.gpu_index,
                                      gpu_name=g.gpu_name, total_memory=g.total_memory_mib))
            else:
                row.gpu_name, row.total_memory, row.is_healthy = g.gpu_name, g.total_memory_mib, True
        worker_id = worker.worker_id
    return {"worker_id": worker_id, "requeued_jobs": requeued}


@router.post("/worker/heartbeat")
def heartbeat(req: HeartbeatRequest, session: Session = Depends(get_session)):
    with session.begin():
        worker = session.get(Worker, req.worker_id, with_for_update=True)
        if worker is None:
            raise HTTPException(404, "unknown worker")
        if worker.status == "OFFLINE":
            # Its jobs were already requeued; it must re-register (and kill old containers).
            raise HTTPException(409, "worker was declared offline; register again")
        worker.last_heartbeat = func.now()
    return {"ok": True}


@router.post("/executions/{execution_id}/started")
def started(execution_id: int, req: StartedRequest, session: Session = Depends(get_session)):
    with session.begin():
        ex = session.get(JobExecution, execution_id, with_for_update=True)
        if ex is None:
            raise HTTPException(404, "unknown execution")
        if ex.status != "ASSIGNED":
            raise HTTPException(409, f"execution is {ex.status}, expected ASSIGNED")
        ex.status, ex.container_id, ex.started_at = "RUNNING", req.container_id, func.now()
        session.get(Job, ex.job_id, with_for_update=True).status = "RUNNING"
    return {"ok": True}


@router.post("/executions/{execution_id}/complete")
def complete(execution_id: int, req: CompleteRequest, session: Session = Depends(get_session)):
    with session.begin():
        ex = session.get(JobExecution, execution_id, with_for_update=True)
        if ex is None:
            raise HTTPException(404, "unknown execution")
        if ex.status not in ACTIVE:
            # Late callback from an attempt that was already failed/requeued: ignore it.
            raise HTTPException(409, f"execution is already {ex.status}")
        final = "COMPLETED" if req.exit_code == 0 else "FAILED"
        ex.status, ex.exit_code, ex.log_path, ex.ended_at = final, req.exit_code, req.log_path, func.now()
        if final == "FAILED":
            ex.failure_reason = f"exit code {req.exit_code}"
        session.get(Job, ex.job_id, with_for_update=True).status = final
    return {"ok": True, "status": final}







