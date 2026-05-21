import base64
import hashlib
import hmac
import os
from typing import Optional


DEMO_USER_ID = "user_demo"
DEMO_EMAIL = "demo@chargebackcopilot.local"
DEMO_NAME = "Demo User"
SESSION_COOKIE = "chargeback_copilot_session"


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, salt_text, digest_text = stored_hash.split("$", 2)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = base64.b64decode(digest_text.encode())
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            base64.b64decode(salt_text.encode()),
            120_000,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def new_session_token() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
