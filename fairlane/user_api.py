import os
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fairlane.auth import CurrentUser, current_user, run_admin
from fairlane.models import Job, JobExecution, User, Worker, WorkerGPU
from fairlane.scheduler import ACTIVE, free_memory_expr
from fairlane.worker_api import get_session

router = APIRouter(prefix="/api")
NFS_ROOT = Path(os.getenv("FAIRLANE_NFS_ROOT", "/srv/fairlane"))
JOB_NAME = r"^[A-Za-z0-9_-]+$"
MAX_SCRIPT = 1024 * 1024


class JobIn(BaseModel):
    job_name: str = Field(min_length=1, max_length=40, pattern=JOB_NAME)
    required_gpu_memory_mib: int = Field(gt=0)


@router.get("/users")
def list_users(session: Session = Depends(get_session)):
    rows = session.execute(select(User.name, User.role, User.unix_user).order_by(User.name)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/my/scripts")
def my_scripts(me: CurrentUser = Depends(current_user)):
    """Job names the logged-in user can submit = folders in their NFS area that contain train.py."""
    base = NFS_ROOT / "users" / me.unix_user
    try:
        return sorted(p.parent.name for p in base.glob("*/train.py"))
    except PermissionError:
        return []


@router.post("/scripts", status_code=201)
async def upload_script(job_name: str = Form(..., max_length=40, pattern=JOB_NAME),
                        file: UploadFile = File(...),
                        me: CurrentUser = Depends(current_user)):
    data = await file.read(MAX_SCRIPT + 1)
    if len(data) > MAX_SCRIPT:
        raise HTTPException(413, "script larger than 1 MiB")
    path = run_admin("putscript", me.unix_user, job_name, data=data)   # written as the user, on NFS
    return {"script_path": path}


@router.post("/jobs", status_code=201)
def submit_job(req: JobIn, me: CurrentUser = Depends(current_user), session: Session = Depends(get_session)):
    rel_path = f"users/{me.unix_user}/{req.job_name}/train.py"
    if not (NFS_ROOT / rel_path).is_file():
        raise HTTPException(400, f"script not found on NFS: {rel_path}")
    with session.begin():
        job = Job(user_id=me.user_id, job_name=req.job_name, script_path=rel_path,
                  priority=1 if me.role == "PROFESSOR" else 5,      # from the token's user, never the client
                  required_gpu_memory=req.required_gpu_memory_mib)
        session.add(job)
        session.flush()
        job_id = job.job_id
    return {"job_id": job_id, "status": "QUEUED"}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, me: CurrentUser = Depends(current_user), session: Session = Depends(get_session)):
    target = None
    with session.begin():
        job = session.get(Job, job_id, with_for_update=True)
        if job is None:
            raise HTTPException(404, "unknown job")
        if job.user_id != me.user_id and me.role != "PROFESSOR":
            raise HTTPException(403, "you can only cancel your own jobs")
        if job.status in ("COMPLETED", "FAILED", "CANCELLED"):
            raise HTTPException(409, f"job is already {job.status}")
        ex = session.scalars(select(JobExecution)
                             .where(JobExecution.job_id == job_id, JobExecution.status.in_(ACTIVE))
                             .with_for_update()).first()
        if ex is not None:
            ex.status, ex.failure_reason, ex.ended_at = "CANCELLED", "cancelled by user", func.now()
            target = (session.get(Worker, ex.worker_id).agent_url, ex.execution_id)
        job.status = "CANCELLED"
    if target:
        try:
            httpx.post(f"{target[0]}/cancel/{target[1]}", timeout=5)
        except httpx.HTTPError:
            pass
    return {"job_id": job_id, "status": "CANCELLED"}


@router.get("/jobs")
def list_jobs(session: Session = Depends(get_session)):
    rows = session.execute(
        select(Job.job_id, Job.job_name, User.name.label("user"), User.role, Job.priority,
               Job.status, Job.required_gpu_memory, Job.submitted_at)
        .join(User, User.user_id == Job.user_id).order_by(Job.job_id.desc()).limit(50)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/executions")
def list_executions(session: Session = Depends(get_session)):
    rows = session.execute(
        select(JobExecution.execution_id, JobExecution.job_id, Job.job_name, Worker.worker_name,
               JobExecution.status, JobExecution.exit_code, JobExecution.failure_reason,
               JobExecution.started_at, JobExecution.ended_at)
        .join(Job, Job.job_id == JobExecution.job_id)
        .join(Worker, Worker.worker_id == JobExecution.worker_id)
        .order_by(JobExecution.execution_id.desc()).limit(20)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/workers")
def list_workers(session: Session = Depends(get_session)):
    reserved, free = free_memory_expr()
    rows = session.execute(
        select(Worker.worker_id, Worker.worker_name, Worker.status, Worker.is_degraded,
               Worker.last_heartbeat, WorkerGPU.gpu_index, WorkerGPU.gpu_name,
               WorkerGPU.total_memory, free.label("free_memory"))
        .join(WorkerGPU, WorkerGPU.worker_id == Worker.worker_id)
        .outerjoin(reserved, reserved.c.gpu_id == WorkerGPU.gpu_id)
        .order_by(Worker.worker_id, WorkerGPU.gpu_index)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/executions/{execution_id}/log")
def execution_log(execution_id: int, lines: int = 50, session: Session = Depends(get_session)):
    ex = session.get(JobExecution, execution_id)
    if ex is None:
        raise HTTPException(404, "unknown execution")
    agent_url = session.get(Worker, ex.worker_id).agent_url
    try:
        r = httpx.get(f"{agent_url}/logs/{execution_id}", params={"lines": lines}, timeout=5)
    except httpx.HTTPError:
        raise HTTPException(502, "worker not reachable")
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)
    return r.json()
