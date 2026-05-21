import os
import re
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .models import EvidenceFile
from .scanning import scan_upload

try:
    import boto3
except ImportError:
    boto3 = None


ALLOWED_UPLOAD_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
    "message/rfc822",
}
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))
UPLOAD_ROOT = Path(os.environ.get("EVIDENCE_UPLOAD_DIR", "backend/uploads")).resolve()
OBJECT_STORAGE_BACKEND = os.environ.get("OBJECT_STORAGE_BACKEND", "local")
OBJECT_STORAGE_BUCKET = os.environ.get("OBJECT_STORAGE_BUCKET", "local-evidence")
OBJECT_STORAGE_REGION = os.environ.get("OBJECT_STORAGE_REGION", "")
OBJECT_STORAGE_ENDPOINT = os.environ.get("OBJECT_STORAGE_ENDPOINT", "")


class EvidenceStorage(Protocol):
    def put(self, *, key: str, data: bytes, content_type: str) -> None:
        ...

    def get(self, *, key: str) -> bytes:
        ...

    def delete(self, *, key: str) -> None:
        ...


class LocalEvidenceStorage:
    def _path_for_key(self, key: str) -> Path:
        target = (UPLOAD_ROOT / key).resolve()
        try:
            target.relative_to(UPLOAD_ROOT)
        except ValueError:
            raise ValueError("Invalid evidence file key.")
        return target

    def put(self, *, key: str, data: bytes, content_type: str) -> None:
        target = self._path_for_key(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def get(self, *, key: str) -> bytes:
        return self._path_for_key(key).read_bytes()

    def delete(self, *, key: str) -> None:
        self._path_for_key(key).unlink(missing_ok=True)


class S3EvidenceStorage:
    def __init__(self) -> None:
        if boto3 is None:
            raise RuntimeError("S3 object storage requires boto3. Install requirements.txt before running.")
        if not OBJECT_STORAGE_BUCKET:
            raise RuntimeError("OBJECT_STORAGE_BUCKET is required for S3 object storage.")
        kwargs = {}
        if OBJECT_STORAGE_REGION:
            kwargs["region_name"] = OBJECT_STORAGE_REGION
        if OBJECT_STORAGE_ENDPOINT:
            kwargs["endpoint_url"] = OBJECT_STORAGE_ENDPOINT
        self.client = boto3.client("s3", **kwargs)

    def put(self, *, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=OBJECT_STORAGE_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )

    def get(self, *, key: str) -> bytes:
        response = self.client.get_object(Bucket=OBJECT_STORAGE_BUCKET, Key=key)
        return response["Body"].read()

    def delete(self, *, key: str) -> None:
        self.client.delete_object(Bucket=OBJECT_STORAGE_BUCKET, Key=key)


def storage_adapter() -> EvidenceStorage:
    if OBJECT_STORAGE_BACKEND == "s3":
        return S3EvidenceStorage()
    if OBJECT_STORAGE_BACKEND == "local":
        return LocalEvidenceStorage()
    raise RuntimeError(f"Unsupported OBJECT_STORAGE_BACKEND: {OBJECT_STORAGE_BACKEND}")


def clean_filename(filename: str) -> str:
    name = Path(filename or "evidence-upload").name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return name or "evidence-upload"


def validate_upload(filename: str, content_type: str, data: bytes) -> None:
    if not data:
        raise ValueError("Choose a file to upload.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File is too large. Limit is {MAX_UPLOAD_BYTES} bytes.")
    if content_type not in ALLOWED_UPLOAD_TYPES:
        raise ValueError("File type is not supported for evidence uploads.")
    clean_filename(filename)


def store_evidence_file(
    *,
    evidence_id: str,
    dispute_id: str,
    owner_id: str,
    filename: str,
    content_type: str,
    data: bytes,
    created_at: str,
) -> EvidenceFile:
    validate_upload(filename, content_type, data)
    scan_status = scan_upload(data)
    safe_name = clean_filename(filename)
    storage_key = f"{owner_id}/{dispute_id}/{uuid4().hex}_{safe_name}"
    storage_adapter().put(key=storage_key, data=data, content_type=content_type)
    return EvidenceFile(
        id=f"file_{uuid4().hex[:12]}",
        evidence_id=evidence_id,
        dispute_id=dispute_id,
        owner_id=owner_id,
        original_filename=safe_name,
        content_type=content_type,
        size_bytes=len(data),
        storage_bucket=OBJECT_STORAGE_BUCKET,
        storage_key=storage_key,
        scan_status=scan_status,
        extraction_status="not_configured",
        created_at=created_at,
    )


def read_evidence_file(file: EvidenceFile) -> bytes:
    return storage_adapter().get(key=file.storage_key)


def remove_evidence_file(file: EvidenceFile) -> None:
    storage_adapter().delete(key=file.storage_key)
