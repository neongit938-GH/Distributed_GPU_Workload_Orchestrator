"""Submit a test job:  uv run python -m scripts.submit Jack my-job 3000"""
import sys

from sqlalchemy import func, select

from fairlane.db import SessionLocal
from fairlane.models import Job, User

user_name, job_name, mib = sys.argv[1], sys.argv[2], int(sys.argv[3])
with SessionLocal() as s, s.begin():
    user = s.scalars(select(User).where(func.lower(User.name) == user_name.lower())).one()
    job = Job(user_id=user.user_id, job_name=job_name, script_path=f"users/{user.name.lower()}/{job_name}/train.py",
              priority=1 if user.role == "PROFESSOR" else 5, required_gpu_memory=mib)
    s.add(job)
    s.flush()
    print(f"submitted job {job.job_id} ({job_name}, {mib} MiB) for {user.name}")




































