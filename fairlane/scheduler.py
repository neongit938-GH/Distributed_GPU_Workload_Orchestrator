import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fairlane.models import Job, JobExecution, Worker, WorkerGPU

ACTIVE = ("ASSIGNED", "RUNNING")
CANDIDATE_JOBS = 10   # how far down the queue we look when the top job doesn't fit


def lock_next_job(session: Session, skip_ids: list[int]) -> Job | None:
    """Oldest QUEUED job that no other scheduler holds and we haven't already tried."""
    stmt = (
        select(Job)
        .where(Job.status == "QUEUED", Job.job_id.not_in(skip_ids))
        .order_by(Job.submitted_at, Job.job_id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return session.scalars(stmt).first()


def free_memory_expr():
    """Subquery: memory already reserved on each GPU by its active executions."""
    reserved = (
        select(JobExecution.gpu_id, func.sum(Job.required_gpu_memory).label("reserved"))
        .join(Job, Job.job_id == JobExecution.job_id)
        .where(JobExecution.status.in_(ACTIVE))
        .group_by(JobExecution.gpu_id)
        .subquery()
    )
    free = WorkerGPU.total_memory - func.coalesce(reserved.c.reserved, 0)
    return reserved, free


def pick_gpu(session: Session, required_mib: int) -> WorkerGPU | None:
    reserved, free = free_memory_expr()
    stmt = (
        select(WorkerGPU)
        .join(Worker, Worker.worker_id == WorkerGPU.worker_id)
        .outerjoin(reserved, reserved.c.gpu_id == WorkerGPU.gpu_id)
        .where(
            Worker.status == "ONLINE",
            Worker.is_degraded.is_(False),
            WorkerGPU.is_healthy.is_(True),
            free >= required_mib,
        )
        .order_by(free.asc(), WorkerGPU.gpu_id)       # best-fit: tightest GPU that still fits
        .limit(1)
        .with_for_update(of=WorkerGPU, skip_locked=True)
    )
    return session.scalars(stmt).first()


def assign_once(session: Session, hold_seconds: float = 0) -> JobExecution | None:
    """One scheduling decision in one transaction: first candidate job that fits a GPU."""
    with session.begin():
        tried: list[int] = []
        while len(tried) < CANDIDATE_JOBS:
            job = lock_next_job(session, tried)
            if job is None:
                return None                       # nothing (unlocked) left in the queue
            gpu = pick_gpu(session, job.required_gpu_memory)
            if gpu is None:
                tried.append(job.job_id)          # doesn't fit anywhere right now: try the next job
                continue
            time.sleep(hold_seconds)              # testing only
            execution = JobExecution(job_id=job.job_id, worker_id=gpu.worker_id, gpu_id=gpu.gpu_id)
            session.add(execution)
            job.status = "ASSIGNED"
            return execution
        return None