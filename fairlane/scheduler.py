import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from fairlane.models import Job, JobExecution, Worker


def pick_next_job(session: Session, lock: bool = False) -> Job | None:
    stmt = (
        select(Job)
        .where(Job.status == "QUEUED")
        .order_by(Job.submitted_at, Job.job_id)
        .limit(1)
    )
    if lock:
        stmt = stmt.with_for_update(skip_locked=True)
    return session.scalars(stmt).first()


def pick_worker(session: Session, lock: bool = False) -> Worker | None:
    stmt = (
        select(Worker)
        .where(Worker.status == "ONLINE", Worker.is_degraded.is_(False))
        .order_by(Worker.worker_id)
        .limit(1)
    )
    if lock:
        stmt = stmt.with_for_update(skip_locked=True)
    return session.scalars(stmt).first()


def assign_once(session: Session, hold_seconds: float = 0) -> JobExecution | None:


    """Make ONE scheduling decision inside ONE transaction."""

    with session.begin():                       # COMMIT on success, ROLLBACK on any exception
        job = pick_next_job(session, lock=True)
        if job is None:
            return None                         # nothing queued
        worker = pick_worker(session, lock=True)
        if worker is None:
            return None                         # no free worker; the job stays QUEUED

        time.sleep(hold_seconds)                # testing only: widens the race window

        execution = JobExecution(job_id=job.job_id, worker_id=worker.worker_id, gpu_index=0)
        session.add(execution)
        job.status = "ASSIGNED"
        worker.status = "BUSY"
    return execution