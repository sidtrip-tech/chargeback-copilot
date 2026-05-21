import json
import time
import traceback
from uuid import uuid4


def new_request_id() -> str:
    return f"req_{uuid4().hex[:16]}"


def now_ms() -> int:
    return int(time.time() * 1000)


def log_event(event: str, **fields) -> None:
    payload = {"event": event, **fields}
    print(json.dumps(payload, sort_keys=True), flush=True)


def safe_error_payload(exc: Exception, request_id: str) -> dict[str, str]:
    return {"error": str(exc), "request_id": request_id}


def exception_summary(exc: Exception) -> dict[str, str]:
    return {
        "error_type": exc.__class__.__name__,
        "error": str(exc),
        "traceback": traceback.format_exc(limit=8),
    }
