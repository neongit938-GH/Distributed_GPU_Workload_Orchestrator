from sqlalchemy import select

from fairlane.db import SessionLocal
from fairlane.models import Job, WorkerGPU
from fairlane.scheduler import assign_once, free_memory_expr

# one fresh session per scheduling pass, like a real scheduler loop
while True:
    with SessionLocal() as session:
        ex = assign_once(session)
        if ex is None:
            break
        print(f"job {ex.job_id} -> worker {ex.worker_id}, gpu {ex.gpu_id}")

with SessionLocal() as session:
    reserved, free = free_memory_expr()
    rows = session.execute(
        select(WorkerGPU.gpu_id, WorkerGPU.worker_id, WorkerGPU.gpu_index, WorkerGPU.total_memory, free)
        .outerjoin(reserved, reserved.c.gpu_id == WorkerGPU.gpu_id)
        .order_by(WorkerGPU.gpu_id)
    ).all()
    print("\ngpu_id worker idx total free")
    for r in rows:
        print(f"{r[0]:>6} {r[1]:>6} {r[2]:>3} {r[3]:>5} {r[4]:>5}")
    print("\nstill queued:", [j.job_name for j in session.scalars(select(Job).where(Job.status == "QUEUED"))])






































