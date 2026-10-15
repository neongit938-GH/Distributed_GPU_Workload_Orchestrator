from sqlalchemy import select

from fairlane.db import SessionLocal
from fairlane.models import Job, User
from fairlane.scheduler import assign_once, effective_priority_expr


def show_queue(title):
    with SessionLocal() as session:
        eff = effective_priority_expr().label("eff")
        rows = session.execute(
            select(Job.job_id, Job.job_name, User.name, Job.priority, eff)
            .join(User, User.user_id == Job.user_id)
            .where(Job.status == "QUEUED")
            .order_by(eff, Job.submitted_at, Job.job_id)
        ).all()
    print(f"\n{title}")
    print(" job  name        user  base  effective")
    for r in rows:
        print(f"{r.job_id:>4}  {r.job_name:<10}  {r.name:<4}  {r.priority:>4}  {r.eff:>9.2f}")


show_queue("Queue before scheduling (lowest effective = runs first):")
print()
while True:
    with SessionLocal() as session:
        ex = assign_once(session)
        if ex is None:
            break
        print(f"assigned job {ex.job_id} -> gpu {ex.gpu_id}")
show_queue("Queue after scheduling:")












