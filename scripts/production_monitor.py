#!/usr/bin/env python3
import json
import os
import sys
import time
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = os.environ.get("MONITOR_BASE_URL", "https://chargeback-copilot.onrender.com").rstrip("/")
TIMEOUT_SECONDS = float(os.environ.get("MONITOR_TIMEOUT_SECONDS", "10"))
EXPECTED_STORAGE_BACKEND = os.environ.get("MONITOR_EXPECTED_STORAGE_BACKEND", "s3")
EXPECTED_DATABASE_BACKEND = os.environ.get("MONITOR_EXPECTED_DATABASE_BACKEND", "postgres")
EXPECT_EMAIL_CONFIGURED = os.environ.get("MONITOR_EXPECT_EMAIL_CONFIGURED", "true").lower() in {"1", "true", "yes"}
EXPECT_AI_CONFIGURED = os.environ.get("MONITOR_EXPECT_AI_CONFIGURED", "false").lower() in {"1", "true", "yes"}
JOB_RUN_TOKEN = os.environ.get("JOB_RUN_TOKEN", "")
JOB_DIAGNOSTICS_LIMIT = int(os.environ.get("MONITOR_JOB_DIAGNOSTICS_LIMIT", "10"))


def fetch_json(path: str, extra_headers: Optional[dict[str, str]] = None) -> dict:
    headers = {"User-Agent": "chargeback-copilot-monitor/1.0", **(extra_headers or {})}
    request = Request(f"{BASE_URL}{path}", headers=headers)
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        body = response.read().decode("utf-8")
        return json.loads(body)


def maybe_print_job_diagnostics(jobs: dict) -> None:
    if jobs.get("healthy", True) or not JOB_RUN_TOKEN:
        return
    try:
        payload = fetch_json(
            f"/api/admin/jobs?limit={JOB_DIAGNOSTICS_LIMIT}",
            extra_headers={"X-Job-Run-Token": JOB_RUN_TOKEN},
        )
        print(
            "JOB DIAGNOSTICS: "
            + json.dumps(
                {
                    "jobs_health": jobs,
                    "recent_jobs": payload.get("jobs", []),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"JOB DIAGNOSTICS UNAVAILABLE: {exc}", file=sys.stderr)


def fail(message: str) -> int:
    print(f"MONITOR FAILED: {message}", file=sys.stderr)
    return 1


def main() -> int:
    started = time.time()
    try:
        health = fetch_json("/api/health")
        if not health.get("ok"):
            return fail("/api/health did not return ok=true")

        readiness = fetch_json("/api/readiness")
        checks = readiness.get("checks", {})
        database = checks.get("database", {})
        storage = checks.get("storage", {})
        email = checks.get("email", {})
        ai = checks.get("ai", {})
        jobs = checks.get("jobs", {})

        if not readiness.get("ok"):
            maybe_print_job_diagnostics(jobs)
            return fail("/api/readiness did not return ok=true")

        if database.get("backend") != EXPECTED_DATABASE_BACKEND:
            return fail(f"database backend was {database.get('backend')!r}, expected {EXPECTED_DATABASE_BACKEND!r}")
        if storage.get("backend") != EXPECTED_STORAGE_BACKEND:
            return fail(f"storage backend was {storage.get('backend')!r}, expected {EXPECTED_STORAGE_BACKEND!r}")
        if EXPECT_EMAIL_CONFIGURED and not email.get("configured"):
            return fail("email delivery is not configured")
        if EXPECT_AI_CONFIGURED and not ai.get("configured"):
            return fail("AI generation is not configured")

        elapsed_ms = int((time.time() - started) * 1000)
        print(
            json.dumps(
                {
                    "ok": True,
                    "base_url": BASE_URL,
                    "elapsed_ms": elapsed_ms,
                    "database": database,
                    "storage": storage,
                    "email": {"configured": email.get("configured"), "host": email.get("host")},
                    "ai": {"configured": ai.get("configured")},
                    "jobs": jobs,
                },
                sort_keys=True,
            )
        )
        return 0
    except HTTPError as exc:
        return fail(f"HTTP {exc.code} from {exc.url}")
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
