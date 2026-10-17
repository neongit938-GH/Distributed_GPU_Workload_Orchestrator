from sqlalchemy import select

from fairlane.db import SessionLocal
from fairlane.models import Job, JobExecution, Worker

with SessionLocal() as s:
    print("WORKERS")
    for w in s.scalars(select(Worker).order_by(Worker.worker_id)):
        print(f"  {w.worker_id:>2} {w.worker_name:<11} {w.status}")
    print("JOBS")
    for j in s.scalars(select(Job).order_by(Job.job_id)):
        print(f"  {j.job_id:>2} {j.job_name:<9} {j.required_gpu_memory:>5} MiB  {j.status}")
    print("EXECUTIONS (latest 10)")
    for e in s.scalars(select(JobExecution).order_by(JobExecution.execution_id.desc()).limit(10)):
        print(f"  {e.execution_id:>2} job {e.job_id} on worker {e.worker_id}  {e.status:<9} {e.failure_reason or ''}")






















