from dataclasses import dataclass

from .models import EvidenceFile


MAX_EXTRACTED_TEXT_CHARS = 50_000
TEXT_CONTENT_TYPES = {
    "message/rfc822",
    "text/plain",
}


@dataclass(frozen=True)
class ExtractionResult:
    status: str
    text: str = ""


def extract_text(file: EvidenceFile, data: bytes) -> ExtractionResult:
    content_type = file.content_type.split(";")[0].strip().lower()
    if content_type not in TEXT_CONTENT_TYPES and not content_type.startswith("text/"):
        return ExtractionResult(status="unsupported")
    text = data.decode("utf-8", errors="replace").strip()
    if not text:
        return ExtractionResult(status="empty")
    return ExtractionResult(status="extracted", text=text[:MAX_EXTRACTED_TEXT_CHARS])
