"""from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Identity, Integer, Text, false, func, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sqlalchemy import Index, text"""

from datetime import datetime

from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, Text,
                        UniqueConstraint, false, func, text, true)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column



class Base(DeclarativeBase):
    pass


class Queue(Base):
    __tablename__ = "queues"
    __table_args__ = (CheckConstraint("guaranteed_memory >= 0", name="ck_queue_guarantee_nonneg"),)

    queue_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    queue_name: Mapped[str] = mapped_column(Text, unique=True)
    guaranteed_memory: Mapped[int] = mapped_column(Integer)   # MiB of GPU memory reserved for this queue



class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('PROFESSOR', 'STUDENT')", name="ck_users_role"),
    )

    user_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)


    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    queue_id: Mapped[int] = mapped_column(ForeignKey("queues.queue_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())



class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED', 'ASSIGNED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_jobs_status",
        ),
        CheckConstraint("required_gpu_memory > 0", name="ck_jobs_gpu_mem_positive"),
    )

    job_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)


    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))


    job_name: Mapped[str] = mapped_column(Text)


    script_path: Mapped[str] = mapped_column(Text)


    priority: Mapped[int] = mapped_column(Integer)


    status: Mapped[str] = mapped_column(Text, server_default="QUEUED")
    required_gpu_memory: Mapped[int] = mapped_column(Integer)  # MiB

    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())









class Worker(Base):
    __tablename__ = "workers"
    __table_args__ = (
        CheckConstraint("status IN ('ONLINE','DRAINING','OFFLINE')", name="ck_workers_status"),
    )

    worker_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)


    worker_name: Mapped[str] = mapped_column(Text, unique=True)


    agent_url: Mapped[str] = mapped_column(Text)


    status: Mapped[str] = mapped_column(Text, server_default="OFFLINE")
    is_degraded: Mapped[bool] = mapped_column(server_default=false())
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkerGPU(Base):
    __tablename__ = "worker_gpus"
    __table_args__ = (
        UniqueConstraint("worker_id", "gpu_index", name="uq_worker_gpu_index"),
        CheckConstraint("total_memory > 0", name="ck_gpu_total_memory_positive"),
    )
    gpu_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.worker_id"))
    gpu_index: Mapped[int] = mapped_column(Integer)          # 0, 1, 2... as the worker sees it
    gpu_name: Mapped[str | None] = mapped_column(Text)
    total_memory: Mapped[int] = mapped_column(Integer)       # MiB
    is_healthy: Mapped[bool] = mapped_column(server_default=true())










class JobExecution(Base):
    __tablename__ = "job_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ASSIGNED','RUNNING','COMPLETED','FAILED','CANCELLED')",
            name="ck_exec_status",
        ),
        # At most ONE active attempt per job, enforced by Postgres itself
        Index(
            "uq_exec_one_active_per_job", "job_id", unique=True,
            postgresql_where=text("status IN ('ASSIGNED','RUNNING')"),
        ),
    )

    execution_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)


    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.job_id"))


    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.worker_id"))


    status: Mapped[str] = mapped_column(Text, server_default="ASSIGNED")

    gpu_id: Mapped[int] = mapped_column(ForeignKey("worker_gpus.gpu_id"))


    container_id: Mapped[str | None] = mapped_column(Text)


    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


    exit_code: Mapped[int | None] = mapped_column(Integer)

    log_path: Mapped[str | None] = mapped_column(Text)


    failure_reason: Mapped[str | None] = mapped_column(Text)























