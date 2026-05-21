#!/usr/bin/env python3
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from chargeback_copilot import store


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("DATABASE_URL is not set. Set it to sqlite:///... or postgresql://...", file=sys.stderr)
        return 1
    store.init_db()
    backend = "Postgres" if store.using_postgres() else "SQLite"
    print(f"{backend} migrations applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
