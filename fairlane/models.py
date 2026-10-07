from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Identity, Integer, Text, false, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


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
        CheckConstraint("status IN ('ONLINE','BUSY','DRAINING','OFFLINE')", name="ck_workers_status"),
    )

    worker_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    worker_name: Mapped[str] = mapped_column(Text, unique=True)
    agent_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="OFFLINE")
    is_degraded: Mapped[bool] = mapped_column(server_default=false())
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))




































