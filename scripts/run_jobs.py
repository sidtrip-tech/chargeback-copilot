#!/usr/bin/env python3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from chargeback_copilot import api


def main() -> int:
    api.boot()
    result = api.run_jobs()
    print(f"Completed {len(result['completed'])} job(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
