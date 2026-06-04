#!/usr/bin/env python3
import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = (
    os.environ.get("OPERATOR_BASE_URL")
    or os.environ.get("MONITOR_BASE_URL")
    or "https://chargeback-copilot.onrender.com"
).rstrip("/")
TIMEOUT_SECONDS = float(os.environ.get("OPERATOR_TIMEOUT_SECONDS", "15"))
JOB_RUN_TOKEN = os.environ.get("JOB_RUN_TOKEN", "")


def request_json(path: str, method: str = "GET") -> dict:
    if not JOB_RUN_TOKEN:
        raise RuntimeError("JOB_RUN_TOKEN is required for operator job commands.")
    request = Request(
        f"{BASE_URL}{path}",
        method=method,
        headers={
            "User-Agent": "chargeback-copilot-operator/1.0",
            "X-Job-Run-Token": JOB_RUN_TOKEN,
        },
    )
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect and retry Chargeback Copilot background jobs.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    list_parser = subcommands.add_parser("list", help="List recent background jobs.")
    list_parser.add_argument("--limit", type=int, default=25, help="Number of jobs to return, max 100.")

    retry_parser = subcommands.add_parser("retry", help="Requeue a failed background job.")
    retry_parser.add_argument("job_id", help="Background job ID to retry.")

    args = parser.parse_args()
    try:
        if args.command == "list":
            payload = request_json(f"/api/admin/jobs?limit={args.limit}")
        else:
            payload = request_json(f"/api/admin/jobs/{args.job_id}/retry", method="POST")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Operator command failed with HTTP {exc.code}: {body}", file=sys.stderr)
        return 1
    except (RuntimeError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Operator command failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
