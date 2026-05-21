import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Set, Tuple


class RateLimitExceeded(Exception):
    pass


class PayloadTooLarge(Exception):
    pass


class OriginNotAllowed(Exception):
    pass


MAX_JSON_BODY_BYTES = int(os.environ.get("MAX_JSON_BODY_BYTES", "65536"))
AUTH_RATE_LIMIT_ATTEMPTS = int(os.environ.get("AUTH_RATE_LIMIT_ATTEMPTS", "10"))
AUTH_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("AUTH_RATE_LIMIT_WINDOW_SECONDS", "60"))
CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "")

_attempts: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)


def check_json_body_size(length: int) -> None:
    if length > MAX_JSON_BODY_BYTES:
        raise PayloadTooLarge(f"Request body is too large. Limit is {MAX_JSON_BODY_BYTES} bytes.")


def check_rate_limit(key: str, action: str, now: Optional[float] = None) -> None:
    now = now if now is not None else time.time()
    window_start = now - AUTH_RATE_LIMIT_WINDOW_SECONDS
    bucket = _attempts[(key, action)]
    while bucket and bucket[0] < window_start:
        bucket.popleft()
    if len(bucket) >= AUTH_RATE_LIMIT_ATTEMPTS:
        raise RateLimitExceeded("Too many attempts. Try again shortly.")
    bucket.append(now)


def reset_rate_limits() -> None:
    _attempts.clear()


def parse_allowed_origins(raw: str = CORS_ALLOWED_ORIGINS) -> set[str]:
    return {item.strip().rstrip("/") for item in raw.split(",") if item.strip()}


def is_allowed_origin(origin: str, host: str, scheme: str, configured: Optional[Set[str]] = None) -> bool:
    if not origin:
        return True
    normalized_origin = origin.rstrip("/")
    allowed = configured if configured is not None else parse_allowed_origins()
    same_origin = f"{scheme}://{host}".rstrip("/")
    return normalized_origin == same_origin or normalized_origin in allowed


def check_origin(origin: str, host: str, scheme: str) -> None:
    if not is_allowed_origin(origin, host, scheme):
        raise OriginNotAllowed("Request origin is not allowed.")
