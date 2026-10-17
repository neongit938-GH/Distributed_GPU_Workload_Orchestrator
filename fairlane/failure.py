from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fairlane.models import Job, JobExecution, Worker

ACTIVE = ("ASSIGNED", "RUNNING")
HEARTBEAT_TIMEOUT_S = 30   # 3 missed heartbeats at a 10 s interval


def requeue_worker_jobs(session: Session, worker_id: int, reason: str) -> list[int]:
    """Fail every active attempt on this worker and put its jobs back in the queue.
    Must be called inside a transaction."""
    executions = session.scalars(
        select(JobExecution)
        .where(JobExecution.worker_id == worker_id, JobExecution.status.in_(ACTIVE))
        .order_by(JobExecution.execution_id)
        .with_for_update()
    ).all()
    for ex in executions:
        ex.status = "FAILED"
        ex.ended_at = func.now()
        ex.failure_reason = reason
        job = session.get(Job, ex.job_id, with_for_update=True)
        job.status = "QUEUED"          # next scheduling pass creates a NEW execution row
    return [ex.job_id for ex in executions]


def reap_dead_workers(session: Session, timeout_s: int = HEARTBEAT_TIMEOUT_S) -> dict[int, list[int]]:
    """Mark workers OFFLINE if their last heartbeat is too old, and requeue their jobs.
    Returns {worker_id: [requeued job_ids]}."""
    with session.begin():
        dead = session.scalars(
            select(Worker)
            .where(
                Worker.status.in_(("ONLINE", "DRAINING")),
                Worker.last_heartbeat < func.now() - timedelta(seconds=timeout_s),
            )
            .order_by(Worker.worker_id)
            .with_for_update(skip_locked=True)
        ).all()
        result = {}
        for worker in dead:
            worker.status = "OFFLINE"
            result[worker.worker_id] = requeue_worker_jobs(
                session, worker.worker_id, "worker lost (heartbeat timeout)"
            )
    return result







