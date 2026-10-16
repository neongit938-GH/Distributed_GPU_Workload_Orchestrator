from fairlane.db import SessionLocal
from fairlane.scheduler import assign_once, cluster_capacity, lock_queues, queue_usage

while True:
    with SessionLocal() as session:
        ex = assign_once(session)
        if ex is None:
            break
        print(f"assigned job {ex.job_id} -> gpu {ex.gpu_id}")

with SessionLocal() as session, session.begin():
    queues = lock_queues(session)
    usage = queue_usage(session)
    capacity = cluster_capacity(session)
    spare = capacity - sum(q.guaranteed_memory for q in queues.values())
    print(f"\ncluster capacity {capacity} MiB, guaranteed {capacity - spare}, spare pool {spare}")
    print("queue        guarantee   used   over-guarantee")
    for q in queues.values():
        used = usage.get(q.queue_id, 0)
        print(f"{q.queue_name:<11}  {q.guaranteed_memory:>9}  {used:>5}  {max(0, used - q.guaranteed_memory):>6}")