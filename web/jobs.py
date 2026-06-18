"""Job registry for Greco Online Phase 2 — async analysis jobs.

A lightweight in-memory job store. One ``Job`` is created per ``POST /analyze``
request; the background worker transitions it through ``QUEUED → RUNNING → DONE``
(or ``FAILED``). The module-level ``_registry`` is the singleton used by the
routes; tests create their own ``JobRegistry()`` instances for isolation.

Durability: jobs survive the request lifecycle but are lost on server restart.
Phase 4 (database) will replace this with persisted rows.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Job:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.QUEUED
    report_id: Optional[int] = None
    error: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    current_move: int = 0
    total_moves: int = 0


class JobRegistry:
    """Thread-safe in-memory job store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}

    def create(self) -> Job:
        """Create a new QUEUED job, register it, and return it."""
        job = Job()
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        """Return the Job for *job_id*, or None if unknown."""
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs) -> None:
        """Update named fields on an existing job. Unknown ids are a no-op."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in kwargs.items():
                setattr(job, key, value)

    def append_log(self, job_id: str, message: str) -> None:
        """Append a progress message to the job's log list."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.logs.append(message)


# The application-wide singleton. Routes import this directly.
_registry = JobRegistry()
