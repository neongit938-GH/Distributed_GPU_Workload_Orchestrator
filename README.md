# Fairlane: A Fair & Fault-Tolerant Scheduler for Distributed ML Workloads

**Team:** OSDBMS-V-2026-T065 | **Domain:** Operating Systems & DBMS | **Academic Session:** 2026–27

---

## 1. Overview

Fairlane is a distributed GPU workload orchestrator designed for small–medium shared GPU environments (labs, research teams, students). It solves the everyday problem of fairly sharing a handful of GPUs among multiple concurrent users—without the heavy infrastructure of enterprise schedulers like Slurm or Run:ai. The system combines **OS scheduling concepts** (priority with aging, process management) with **DBMS techniques** (row-level locking, ACID transactions, concurrency control) to provide:

- Centralized job submission and queueing
- Priority-aware, starvation-free scheduling
- Fault‑tolerant execution across worker nodes
- Real‑time dashboard for monitoring and control

---

## 2. Problem Statement

> Designing a system to automatically queue, schedule, and allocate shared GPU resources efficiently among concurrent user processes.

Without an automated and fair way to share limited GPUs, users face:
- Unpredictable wait times
- Idle GPUs while jobs pile up
- A single user monopolizing the system (intentionally or not)
- No visibility into job status or worker health
- No recovery when a worker node fails or becomes overloaded

Enterprise tools solve this only at large scale, requiring Kubernetes and dedicated teams—unrealistic for academic labs or small teams.

---

## 3. Motivation

- Academic labs frequently share a handful of GPUs among many students and researchers.
- Lightweight, self‑hosted solutions are missing; existing tools are either too heavy or require deep expertise.
- This project bridges **Operating Systems** and **DBMS** in a practical, hands‑on way:
  - **OS side:** scheduling algorithms, process isolation, resource monitoring
  - **DBMS side:** consistent state management, locking, concurrency control

---

## 4. Solution Approach

### 4.1 High‑Level Architecture

```
┌─────────────┐   submits jobs    ┌──────────────────┐   dispatch   ┌────────────────┐
│   User      │ ─────────────────►│   Dashboard      │ ───────────► │  Central Server │
└─────────────┘                   └──────────────────┘             └───────┬────────┘
                                        ▲                        reads/writes │
                                        │                           ┌───────▼────────┐
                                        └── updates statuses ──────►│  PostgreSQL     │
                                                                     └────────────────┘
                                                                              ▲
   ┌───────────────┐          ┌───────────────────┐                           │
   │  Worker Agent │ ◄───────│  NFS Shared Storage│ ◄──── (job scripts/files) ┘
   └───────┬───────┘          └───────────────────┘      Users upload scripts here
           │ executes jobs
```

**Key components**

- **Dashboard:** User interface for job submission, status tracking, and role‑based access (student/professor).
- **Central Server:** Manages API, scheduling logic, worker coordination, and failure handling.
- **Worker Agents:** Execute jobs as native OS processes and report telemetry (GPU, CPU, RAM usage).
- **Database (PostgreSQL):** Stores users, jobs, execution logs, and worker status with row‑level locks ensuring atomicity.

### 4.2 Workflow

1. **User prepares job** – places script/data in shared NFS folder.
2. **Submit** – user submits the job path and resource requirements via dashboard.
3. **Scheduler** – priority‑with‑aging algorithm picks next job, considering fairness and resource availability.
4. **Dispatch** – central server atomically claims the job in the DB, sends it to a free worker.
5. **Execution** – worker runs the job, streams logs/status, and stores outputs back to NFS.
6. **Failure handling** – if a worker crashes, the job is re‑queued or flagged; heartbeats detect health.

### 4.3 Scheduling Logic

- **Priority with Aging:** Each job has a base priority; waiting time increases its effective priority so no job starves.
- **Queue Management:** Jobs are stored in PostgreSQL with row‑level locks to avoid double‑dispatch.
- **Fairness:** Users are limited to a maximum number of concurrent jobs; aging guarantees eventual execution.

---

## 5. Features

- **Job Submission:** Upload scripts to NFS and submit in a few clicks.
- **Job Status Tracking:** Real‑time view of queue, running, or completed status.
- **Role‑Based Access:** Separate views for students and professors.
- **Resource Dashboard:** Live GPU, CPU, and RAM usage across workers.
- **Fault Tolerance:** Automated detection of worker failures and re‑queueing.
- **Scalable Worker Pool:** New workers can join dynamically without code changes.

---

## 6. Technology Stack

| Component       | Technology                                      |
|-----------------|-------------------------------------------------|
| Backend         | Python, FastAPI                                |
| Main workers    | Python (subprocess) + C++ for low‑level control |
| Database        | PostgreSQL (with row‑level locking, ACID)      |
| Storage         | NFS (shared folder)                            |
| Monitoring      | NVML (NVIDIA Management Library)               |
| ORM             | SQLAlchemy                                     |
| Containerization| Docker (for workers)                           |
| Version Control | Git / GitHub                                   |
| IDE             | VS Code                                        |

---

## 7. Development Methodology

1. **Requirement Analysis:** Identifying resource bottlenecks, queue rules, and failure scenarios.
2. **System Design:** Architecture, DB schema, scheduling algorithm design.
3. **Implementation:** Central server, worker agents, dashboard.
4. **Testing:** Simulating OOM crashes, race conditions, node overloads, and multi‑user contention.

---

## 8. Team & Contributions

| Member               | Role                | Primary Contribution              |
|----------------------|---------------------|-----------------------------------|
| Vansh Sagar          | Team Lead           | Workflows, coordination           |
| Suryansh Bhatnagar   | Dashboard / UI      | Frontend, Excel/status sheets     |
| Harshvardhan Sharma  | Database Admin      | Architecture, PostgreSQL schema   |
| Vansh Garg           | Testing / Docs      | Documentation, test scenarios     |

**Mentor:** Dr. Ashwini Kumar  
**Interactions completed:** 3 (as of Phase‑I)

---

## 9. Roadmap

- **Phase‑I (Proposal & Design):** Problem analysis, architecture, DB schema, scheduling plan ✔
- **Phase‑II (Development):** Implement central server, worker agents, dashboard; initial testing
- **Phase‑III (Final):** Full integration, stress testing, performance tuning, final report

---

## 10. Expected Outcomes

- A functional, fault‑tolerant distributed GPU workload orchestrator with a live dashboard.
- Efficient task queue management and fair job scheduling **without starvation**.
- Measurable fairness metrics and recovery behavior from simulated failures.
- A system easily extendable to real shared‑GPU labs.

---

## 11. Installation & Running (Planned)

> *Work in progress – final steps will be added after Phase‑II.*

```bash
# 1. Clone repository
git clone https://github.com/neongit938-GH/Distributed_GPU_Workload_Orchestrator.git
cd Distributed_GPU_Workload_Orchestrator

# 2. Set up database (PostgreSQL)
createdb fairlane
# apply schema.sql

# 3. Configure NFS mount (if not already)
mount -t nfs <server>:/shared /mnt/nfs

# 4. Run central server
python server.py

# 5. Start worker agent on each GPU machine
python worker.py

# 6. Access dashboard at
http://localhost:8000
```

---

## 12. References

- NVIDIA Run:ai – [https://run‑ai‑docs.nvidia.com/saas](https://run-ai-docs.nvidia.com/saas)
- NVIDIA Slinky (Slurm‑on‑Kubernetes) – [https://developer.nvidia.com/blog/running‑large‑scale‑gpu‑workloads‑on‑kubernetes‑with‑slurm/](https://developer.nvidia.com/blog/running-large-scale-gpu-workloads-on-kubernetes-with-slurm/)
- Volcano – [https://volcano.sh/docs](https://volcano.sh/docs)
- PostgreSQL Explicit Locking – [https://www.postgresql.org/docs/current/explicit‑locking.html](https://www.postgresql.org/docs/current/explicit-locking.html)
- FastAPI – [https://fastapi.tiangolo.com/async/](https://fastapi.tiangolo.com/async/)
- Celery (queue pattern reference) – [https://docs.celeryq.dev/en/stable/](https://docs.celeryq.dev/en/stable/)
- Python `subprocess` – [https://docs.python.org/3/library/subprocess.html](https://docs.python.org/3/library/subprocess.html)

---

## 13. License

To be determined. For academic/educational use.

---

**Questions?** Reach out to the team at `OSDBMS-V-2026-T065` (internal) or via the GitHub repository issues.
