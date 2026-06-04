from dataclasses import asdict, replace
from typing import Any, Dict, List
from uuid import uuid4

from .models import BackgroundJob
from .extraction import extract_text
from .store import get_evidence_file, get_queued_jobs, list_background_jobs, save_background_job, save_evidence_file
from .uploads import read_evidence_file


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


def _process_post_upload_job(job: BackgroundJob) -> None:
    file_id = job.payload.get("file_id", "")
    file = get_evidence_file(job.owner_id, file_id)
    if not file:
        raise ValueError("Evidence file not found for post-upload processing.")
    result = extract_text(file, read_evidence_file(file))
    save_evidence_file(replace(file, extraction_status=result.status, extracted_text=result.text))


def _process_job(job: BackgroundJob) -> None:
    if job.job_type == "evidence_file.post_upload_processing":
        _process_post_upload_job(job)


def run_once(now: str, limit: int = 10) -> List[BackgroundJob]:
    completed = []
    for job in get_queued_jobs(limit):
        started = replace(job, status="running", attempts=job.attempts + 1, updated_at=now)
        save_background_job(started)
        try:
            _process_job(started)
            finished = replace(started, status="completed", last_error="", updated_at=now)
        except Exception as exc:
            finished = replace(started, status="failed", last_error=str(exc), updated_at=now)
        save_background_job(finished)
        completed.append(finished)
    return completed
