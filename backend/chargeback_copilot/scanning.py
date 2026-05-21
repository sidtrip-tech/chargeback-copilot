import os


EICAR_SIGNATURE = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR"
VIRUS_SCAN_ENABLED = os.environ.get("VIRUS_SCAN_ENABLED", "false").lower() in {"1", "true", "yes"}
VIRUS_SCAN_MODE = os.environ.get("VIRUS_SCAN_MODE", "basic")


class UnsafeUpload(Exception):
    pass


def scan_upload(data: bytes) -> str:
    if not VIRUS_SCAN_ENABLED:
        return "not_configured"
    if VIRUS_SCAN_MODE != "basic":
        raise RuntimeError(f"Unsupported VIRUS_SCAN_MODE: {VIRUS_SCAN_MODE}")
    if EICAR_SIGNATURE in data:
        raise UnsafeUpload("Uploaded file failed the safety scan.")
    return "clean"
