from fairlane.db import SessionLocal
from fairlane.scheduler import pick_next_job, pick_worker




with SessionLocal() as session:

    job = pick_next_job(session)

    worker = pick_worker(session)

    print("next job:", job.job_name if job else None)
    print("worker: ", worker.worker_name if worker else None)
