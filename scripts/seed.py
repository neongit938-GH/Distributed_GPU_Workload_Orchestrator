from datetime import datetime, timedelta, timezone

from fairlane.db import SessionLocal
from fairlane.models import Job, Queue, User, Worker, WorkerGPU


def main():
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        profs = Queue(queue_name="Professors", guaranteed_memory=8192)
        students = Queue(queue_name="Students", guaranteed_memory=6144)
        session.add_all([profs, students])
        session.flush()

        jack = User(name="Jack", email="jack@example.com", password_hash="x", role="STUDENT",
                    queue_id=students.queue_id)
        jane = User(name="Jane", email="jane@example.com", password_hash="x", role="PROFESSOR", queue_id=profs.queue_id)
        session.add_all([jack, jane])

        node1 = Worker(worker_name="gpu-node-1", agent_url="http://10.0.0.11:8001", status="ONLINE", last_heartbeat=now)
        node2 = Worker(worker_name="gpu-node-2", agent_url="http://10.0.0.12:8001", status="ONLINE", last_heartbeat=now)
        node3 = Worker(worker_name="gpu-node-3", agent_url="http://10.0.0.13:8001", status="DRAINING", last_heartbeat=now)
        session.add_all([node1, node2, node3])
        session.flush()   # get user_id / worker_id values

        session.add_all([
            WorkerGPU(worker_id=node1.worker_id, gpu_index=0, gpu_name="GTX 1050 Ti", total_memory=4096),
            WorkerGPU(worker_id=node2.worker_id, gpu_index=0, gpu_name="RTX 3060", total_memory=12288),
            WorkerGPU(worker_id=node2.worker_id, gpu_index=1, gpu_name="RTX 3060", total_memory=12288, is_healthy=False),
            WorkerGPU(worker_id=node3.worker_id, gpu_index=0, gpu_name="RTX 3060", total_memory=12288),
        ])

        def job(user, name, mib, minutes_ago):
            return Job(user_id=user.user_id, job_name=name, script_path=f"users/{user.name.lower()}/{name}/train.py",
                       priority=5 if user.role == "STUDENT" else 1, required_gpu_memory=mib,
                       submitted_at=now - timedelta(minutes=minutes_ago))

        session.add_all([
            job(jack, "huge-llm", 16000, 30),     # fits nowhere (biggest healthy GPU has 12288)
            job(jack, "mnist-a", 3000, 20),
            job(jane, "cifar-b", 6000, 15),
            job(jack, "bench-c", 2000, 10),
            job(jane, "cifar-d", 5000, 5),
        ])
        session.commit()


if __name__ == "__main__":
    main()