from typing import Iterable, List, Tuple

from .models import EvidenceGap, Packet


def readiness_score(checklist: Iterable[dict]) -> int:
    items = list(checklist)
    required = [item for item in items if item["required"]]
    if not required:
        return 100
    satisfied = [item for item in required if item["satisfied"]]
    return round((len(satisfied) / len(required)) * 100)


def evidence_progress(checklist: Iterable[dict]) -> Tuple[int, int]:
    items = list(checklist)
    required = [item for item in items if item["required"]]
    return sum(1 for item in required if item["satisfied"]), len(required)


def derived_status(packet: Packet, gaps: List[EvidenceGap]) -> str:
    has_high_gap = any(gap.severity == "high" for gap in gaps)
    if packet and not packet.validation_errors and not has_high_gap and packet.status == "ready":
        return "completed"
    return "in_progress"


def next_step_prompts(packet: Packet, gaps: List[EvidenceGap]) -> List[str]:
    prompts: List[str] = []
    if any(gap.severity == "high" for gap in gaps):
        prompts.append("Add evidence for the high-priority gaps before exporting.")
    if not packet:
        prompts.append("Generate a packet after the evidence checklist is in good shape.")
    elif packet.validation_errors:
        prompts.append("Review cited claims and remove or fix unsupported statements.")
    elif packet.status == "ready":
        prompts.append("Export the packet and submit it through your issuer's official channel.")
        prompts.append("After the issuer responds, record the real-life outcome for your own tracking.")
    return prompts or ["Review the packet details and keep your evidence current."]
