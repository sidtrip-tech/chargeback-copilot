from dataclasses import asdict, replace
from typing import Any, Dict, List
from uuid import uuid4

from .models import BackgroundJob
from .store import get_queued_jobs, list_background_jobs, save_background_job


def enqueue_job(owner_id: str, job_type: str, payload: Dict[str, str], now: str) -> BackgroundJob:
    job = BackgroundJob(
        id=f"job_{uuid4().hex[:12]}",
        owner_id=owner_id,
        job_type=job_type,
        status="queued",
        attempts=0,
        payload=payload,
        last_error="",
        run_after=now,
        created_at=now,
        updated_at=now,
    )
    save_background_job(job)
    return job


def list_jobs(owner_id: str) -> Dict[str, Any]:
    return {"jobs": [asdict(job) for job in list_background_jobs(owner_id)]}


def run_once(now: str, limit: int = 10) -> List[BackgroundJob]:
    completed = []
    for job in get_queued_jobs(limit):
        started = replace(job, status="running", attempts=job.attempts + 1, updated_at=now)
        save_background_job(started)
        # Placeholder worker. Future implementations route by job_type.
        finished = replace(started, status="completed", updated_at=now)
        save_background_job(finished)
        completed.append(finished)
    return completed
