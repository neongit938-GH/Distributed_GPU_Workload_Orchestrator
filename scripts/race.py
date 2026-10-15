import threading
import time

from fairlane.db import SessionLocal, engine
from fairlane.scheduler import assign_once



engine.echo = False   # two threads' SQL logs would interleave into noise


def run(name: str) -> None:

    start = time.perf_counter()

    with SessionLocal() as session:

        ex = assign_once(session, hold_seconds=3)
        took = time.perf_counter() - start



        if ex:
            print(f"[{name}] job {ex.job_id} -> worker {ex.worker_id}, gpu {ex.gpu_id}   ({took:.1f}s)")
        else:
            print(f"[{name}] nothing assigned   ({took:.1f}s)")





threads = [threading.Thread(target=run, args=(n,)) for n in ("A", "B")]


for t in threads:
    t.start()
for t in threads:
    t.join()