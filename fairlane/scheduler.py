from sqlalchemy import select
from sqlalchemy.orm import Session
from fairlane.models import Job, Worker



def pick_next_job(session: Session) -> Job | None:


    stmt = (
        select(Job)
        .where(Job.status == "QUEUED")
        .order_by(Job.submitted_at, Job.job_id) # job_id is for breaking ties
        .limit(1)
    )

    return session.scalars(stmt).first()



def pick_worker(session: Session) -> Worker | None:
    stmt = (
        select(Worker)
        .where(Worker.status == "ONLINE", Worker.is_degraded.is_(False))
        .order_by(Worker.worker_id)
        .limit(1)
    )

    return session.scalars(stmt).first()