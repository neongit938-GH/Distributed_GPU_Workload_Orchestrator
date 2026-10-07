from datetime import datetime, timedelta, timezone
from unicodedata import name

from fairlane.db import SessionLocal
from fairlane.models import Job, User, Worker


def main():
    now = datetime.now(timezone.utc)


    tie = now - timedelta(minutes=10)


    with SessionLocal() as session:
        jack = User(name="Jack", email="alice@example.com", password_hash="x", role="STUDENT")
        jane = User(name="Jane", email="jane@example.com", password_hash="x", role="PROFESSOR")
        session.add_all([jack, jane])

        session.flush()

        session.add_all([
            Worker(worker_name="gpu-node-1", agent_url="http://10.0.0.11:8001",
                   status="ONLINE", last_heartbeat=now),

            Worker(worker_name="gpu-node-2", agent_url="http://10.0.0.12:8001",
                   status="DRAINING", last_heartbeat=now),

            Worker(worker_name="gpu-node-3", agent_url="http://10.0.0.13:8001",
                   status="ONLINE", is_degraded=True, last_heartbeat=now),
        ])



        session.add_all(
            [
                Job(user_id=jack.user_id, job_name="mnist-old", script_path="users/jack/job_1/train.py",
                    priority=5, required_gpu_memory=2000, status="RUNNING",
                    submitted_at=now - timedelta(minutes=30)),

                Job(user_id=jack.user_id, job_name="mnist-b", script_path="users/jack/job_2/train.py",
                    priority=5, required_gpu_memory=2000, submitted_at=tie),

                Job(user_id=jane.user_id, job_name="cifar-p", script_path="users/jane/job_3/train.py",
                    priority=1, required_gpu_memory=4000, submitted_at=tie),

                Job(user_id=jack.user_id, job_name="bench-c", script_path="users/jack/job_4/train.py",
                    priority=5, required_gpu_memory=1000, submitted_at=now - timedelta(minutes=5)),

                Job(user_id=jane.user_id, job_name="cifar-q", script_path="users/jane/job_5/train.py",
                    priority=1, required_gpu_memory=3000, submitted_at=now - timedelta(minutes=1)),
            ]
        )

        session.commit()


if __name__ == "__main__":
    main()