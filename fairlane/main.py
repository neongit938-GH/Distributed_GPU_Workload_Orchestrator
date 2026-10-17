import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fairlane.db import SessionLocal
from fairlane.dispatch import dispatch
from fairlane.failure import reap_dead_workers
from fairlane.scheduler import assign_once
from fairlane.worker_api import router as worker_router

log = logging.getLogger("uvicorn.error")
REAPER_INTERVAL_S = 10
SCHEDULER_INTERVAL_S = 2


def reap_once():
    with SessionLocal() as session:
        return reap_dead_workers(session)


def schedule_once():
    """Assign everything that fits right now, then dispatch each assignment."""
    assigned = []
    while True:
        with SessionLocal() as session:          # fresh session per decision
            ex = assign_once(session)
            if ex is None:
                break
            assigned.append((ex.execution_id, ex.job_id, ex.worker_id))
    return [(eid, jid, wid, dispatch(eid)) for eid, jid, wid in assigned]


async def reaper_loop():
    while True:
        try:
            for worker_id, jobs in (await asyncio.to_thread(reap_once)).items():
                log.warning("worker %s declared OFFLINE, requeued jobs %s", worker_id, jobs)
        except Exception:
            log.exception("reaper pass failed")
        await asyncio.sleep(REAPER_INTERVAL_S)


async def scheduler_loop():
    while True:
        try:
            for eid, jid, wid, ok in await asyncio.to_thread(schedule_once):
                if ok:
                    log.info("job %s -> worker %s (execution %s) dispatched", jid, wid, eid)
                else:
                    log.warning("job %s -> worker %s (execution %s) dispatch FAILED, requeued", jid, wid, eid)
        except Exception:
            log.exception("scheduler pass failed")
        await asyncio.sleep(SCHEDULER_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [asyncio.create_task(reaper_loop()), asyncio.create_task(scheduler_loop())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Fairlane central server", lifespan=lifespan)
app.include_router(worker_router)


































