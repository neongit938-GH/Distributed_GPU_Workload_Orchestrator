import time

from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session, aliased

from fairlane.models import Job, JobExecution, Queue, User, Worker, WorkerGPU

ACTIVE = ("ASSIGNED", "RUNNING")
CANDIDATE_JOBS = 10   # how far down the queue we look when the top job doesn't fit

# Effective priority tuning (provisional, tune by experiment later)
AGING_PER_MINUTE = 0.067   # 4-point gap closes in about 60 minutes of waiting
HOG_PENALTY = 1.0          # one active job counts like about 15 minutes of waiting


def effective_priority_expr():
    """priority - aging * minutes_waited + hog_penalty * user's active jobs  (lower = more urgent)"""
    other = aliased(Job)
    active_jobs_of_user = (
        select(func.count())
        .where(other.user_id == Job.user_id, other.status.in_(ACTIVE))
        .correlate(Job)
        .scalar_subquery()
    )
    minutes_waited = func.extract("epoch", func.now() - Job.submitted_at) / 60.0
    return (
        cast(Job.priority, Float)
        - AGING_PER_MINUTE * minutes_waited
        + HOG_PENALTY * active_jobs_of_user
    )


def lock_next_job(session: Session, skip_ids: list[int]) -> Job | None:
    """Most urgent QUEUED job that no other scheduler holds and we haven't already tried."""
    stmt = (
        select(Job)
        .where(Job.status == "QUEUED", Job.job_id.not_in(skip_ids))
        .order_by(effective_priority_expr(), Job.submitted_at, Job.job_id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return session.scalars(stmt).first()


def free_memory_expr():
    """Subquery: memory already reserved on each GPU by its active executions."""
    reserved = (
        select(JobExecution.gpu_id, func.sum(Job.required_gpu_memory).label("reserved"))
        .join(Job, Job.job_id == JobExecution.job_id)
        .where(JobExecution.status.in_(ACTIVE))
        .group_by(JobExecution.gpu_id)
        .subquery()
    )
    free = WorkerGPU.total_memory - func.coalesce(reserved.c.reserved, 0)
    return reserved, free


def pick_gpu(session: Session, required_mib: int) -> WorkerGPU | None:
    reserved, free = free_memory_expr()
    stmt = (
        select(WorkerGPU)
        .join(Worker, Worker.worker_id == WorkerGPU.worker_id)
        .outerjoin(reserved, reserved.c.gpu_id == WorkerGPU.gpu_id)
        .where(
            Worker.status == "ONLINE",
            Worker.is_degraded.is_(False),
            WorkerGPU.is_healthy.is_(True),
            free >= required_mib,
        )
        .order_by(free.asc(), WorkerGPU.gpu_id)       # best-fit: tightest GPU that still fits
        .limit(1)
        .with_for_update(of=WorkerGPU, skip_locked=True)
    )
    return session.scalars(stmt).first()


def lock_queues(session: Session) -> dict[int, Queue]:
    """Lock every queue row (always in queue_id order). Quotas are a shared limit, so
    quota checks must not run at the same time in two schedulers."""
    queues = session.scalars(select(Queue).order_by(Queue.queue_id).with_for_update())
    return {q.queue_id: q for q in queues}


def cluster_capacity(session: Session) -> int:
    """Total memory of healthy GPUs on ONLINE, non-degraded workers."""
    stmt = (
        select(func.coalesce(func.sum(WorkerGPU.total_memory), 0))
        .join(Worker, Worker.worker_id == WorkerGPU.worker_id)
        .where(Worker.status == "ONLINE", Worker.is_degraded.is_(False), WorkerGPU.is_healthy.is_(True))
    )
    return session.scalar(stmt)


def queue_usage(session: Session) -> dict[int, int]:
    """GPU memory currently reserved by each queue's active jobs."""
    stmt = (
        select(User.queue_id, func.sum(Job.required_gpu_memory))
        .join(User, User.user_id == Job.user_id)
        .where(Job.status.in_(ACTIVE))
        .group_by(User.queue_id)
    )
    return {qid: used for qid, used in session.execute(stmt)}


def quota_allows(session: Session, queues: dict[int, Queue], queue_id: int, mib: int) -> bool:
    """A queue may use its guarantee, plus whatever is left of the shared spare pool."""
    usage = queue_usage(session)
    guarantee = {qid: q.guaranteed_memory for qid, q in queues.items()}
    spare = max(0, cluster_capacity(session) - sum(guarantee.values()))

    def over(qid: int) -> int:                       # how far a queue is already into the spare pool
        return max(0, usage.get(qid, 0) - guarantee[qid])

    spare_left = spare - sum(over(qid) for qid in queues)
    extra_needed = max(0, usage.get(queue_id, 0) + mib - guarantee[queue_id]) - over(queue_id)
    return extra_needed <= spare_left


def assign_once(session: Session, hold_seconds: float = 0) -> JobExecution | None:
    """One scheduling decision in one transaction: first candidate job that fits a GPU and its quota."""
    with session.begin():
        queues = lock_queues(session)             # lock order: queues -> job -> gpu, same in every scheduler
        tried: list[int] = []
        while len(tried) < CANDIDATE_JOBS:
            job = lock_next_job(session, tried)
            if job is None:
                return None                       # nothing (unlocked) left in the queue
            gpu = pick_gpu(session, job.required_gpu_memory)
            if gpu is None:
                tried.append(job.job_id)          # doesn't fit anywhere right now: try the next job
                continue
            queue_id = session.get(User, job.user_id).queue_id
            if not quota_allows(session, queues, queue_id, job.required_gpu_memory):
                tried.append(job.job_id)          # queue is over its share: try the next job
                continue
            time.sleep(hold_seconds)              # testing only
            execution = JobExecution(job_id=job.job_id, worker_id=gpu.worker_id, gpu_id=gpu.gpu_id)
            session.add(execution)
            job.status = "ASSIGNED"
            return execution
        return None