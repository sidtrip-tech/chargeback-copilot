#!/usr/bin/env python3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from chargeback_copilot import api
from chargeback_copilot.observability import exception_summary, log_event


def main() -> int:
    try:
        api.boot()
        result = api.run_jobs()
        log_event("jobs.run.completed", **result["summary"])
        for job in result["completed"]:
            if job["status"] in {"failed", "queued"}:
                log_event(
                    "jobs.run.job_not_completed",
                    job_id=job["id"],
                    job_type=job["job_type"],
                    owner_id=job["owner_id"],
                    status=job["status"],
                    attempts=job["attempts"],
                    run_after=job["run_after"],
                    last_error=job["last_error"],
                )
        return 0
    except Exception as exc:
        log_event("jobs.run.error", **exception_summary(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
