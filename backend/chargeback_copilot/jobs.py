import os
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from uuid import uuid4

from .models import BackgroundJob
from .extraction import extract_text
from .store import get_evidence_file, get_queued_jobs, list_background_jobs, save_background_job, save_evidence_file
from .uploads import read_evidence_file


MAX_JOB_ATTEMPTS = int(os.environ.get("MAX_JOB_ATTEMPTS", "3"))
RETRY_BASE_SECONDS = int(os.environ.get("JOB_RETRY_BASE_SECONDS", "60"))
RETRY_MAX_SECONDS = int(os.environ.get("JOB_RETRY_MAX_SECONDS", "3600"))


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _retry_run_after(now: str, attempts: int) -> str:
    delay = min(RETRY_BASE_SECONDS * (2 ** max(attempts - 1, 0)), RETRY_MAX_SECONDS)
    return _format_utc(_parse_utc(now) + timedelta(seconds=delay))


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
    for job in get_queued_jobs(now, limit):
        started = replace(job, status="running", attempts=job.attempts + 1, updated_at=now)
        save_background_job(started)
        try:
            _process_job(started)
            finished = replace(started, status="completed", last_error="", updated_at=now)
        except Exception as exc:
            if started.attempts >= MAX_JOB_ATTEMPTS:
                finished = replace(started, status="failed", last_error=str(exc), updated_at=now)
            else:
                finished = replace(
                    started,
                    status="queued",
                    last_error=str(exc),
                    run_after=_retry_run_after(now, started.attempts),
                    updated_at=now,
                )
        save_background_job(finished)
        completed.append(finished)
    return completed
