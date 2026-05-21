#!/usr/bin/env python3
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from chargeback_copilot import api
from chargeback_copilot.auth import DEMO_USER_ID


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith(("postgresql://", "postgres://")):
        print("DATABASE_URL must point to a Postgres database for this smoke test.", file=sys.stderr)
        return 1

    api.boot()
    health = api.health()
    if not health["ok"]:
        print("Health check failed.", file=sys.stderr)
        return 1

    login = api.demo_login()
    current_user = api.current_user(login["token"])
    if current_user["id"] != DEMO_USER_ID:
        print("Demo session did not resolve to the demo user.", file=sys.stderr)
        return 1

    listing = api.list_cases(current_user["id"])
    if listing["summary"]["total"] < 1:
        print("Expected seeded demo disputes in staging Postgres.", file=sys.stderr)
        return 1

    first = listing["disputes"][0]
    detail = api.detail(first["id"], current_user["id"])
    if detail["dispute"]["id"] != first["id"]:
        print("Could not load first dispute detail.", file=sys.stderr)
        return 1

    print(
        "Postgres smoke ok: "
        f"{listing['summary']['total']} disputes, "
        f"{listing['summary']['in_progress']} in progress, "
        f"{listing['summary']['completed']} completed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
