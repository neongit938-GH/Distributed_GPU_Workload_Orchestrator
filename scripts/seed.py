from datetime import datetime, timedelta, timezone

from fairlane.db import SessionLocal
from fairlane.models import Job, Queue, User, Worker, WorkerGPU

from fairlane.auth import hasher
DEMO_PW = hasher.hash("demo123")

def main():


    now = datetime.now(timezone.utc)




    with SessionLocal() as session:


        profs = Queue(queue_name="Professors", guaranteed_memory=8192)

        students = Queue(queue_name="Students", guaranteed_memory=6144)


        session.add_all([profs, students])
        session.flush()

        vansh = User(name="Vansh", email="vansh@example.com", password_hash=DEMO_PW, role="STUDENT",
                     unix_user="fl_vansh", queue_id=students.queue_id)
        surya = User(name="Suryansh", email="suryansh@example.com", password_hash=DEMO_PW, role="STUDENT",
                     unix_user="fl_suryansh", queue_id=students.queue_id)
        prof = User(name="Prof", email="prof@example.com", password_hash=DEMO_PW, role="PROFESSOR",
                    unix_user="fl_prof", queue_id=profs.queue_id)
        session.add_all([vansh, surya, prof])



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
            return Job(user_id=user.user_id, job_name=name, script_path=f"users/{user.unix_user}/{name}/train.py",
                       priority=5 if user.role == "STUDENT" else 1, required_gpu_memory=mib,
                       submitted_at=now - timedelta(minutes=minutes_ago))




        session.add_all([
            job(vansh, "linreg", 3000, 20),
            job(surya, "linreg", 3000, 15),
            job(prof, "linreg", 6000, 10),
            job(surya, "crash", 2000, 8),
        ])
        session.commit()
















if __name__ == "__main__":
    main()