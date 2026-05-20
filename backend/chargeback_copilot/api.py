from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
from typing import Any, Dict
from uuid import uuid4

from .models import ConsumerDispute, EvidenceArtifact
from .packets import generate_template_packet
from .planning import checklist_status, find_gaps, get_plan
from .store import (
    get_dispute,
    get_latest_packet,
    init_db,
    list_disputes,
    list_evidence,
    save_dispute,
    save_evidence,
    save_packet,
)
from .timeline import build_timeline
from .validation import export_readiness


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def boot() -> None:
    init_db()


def list_cases() -> Dict[str, Any]:
    return {"disputes": [asdict(dispute) for dispute in list_disputes()]}


def detail(dispute_id: str) -> Dict[str, Any]:
    dispute = get_dispute(dispute_id)
    artifacts = list_evidence(dispute_id)
    plan = get_plan(dispute.category)
    gaps = find_gaps(plan, artifacts)
    packet = get_latest_packet(dispute_id)
    ready, reason = export_readiness(
        packet.validation_errors if packet else [],
        any(gap.severity == "high" for gap in gaps),
        packet is not None,
    )
    return {
        "dispute": asdict(dispute),
        "plan": {
            "category": plan.category,
            "label": plan.label,
            "description": plan.description,
            "careful_guidance": plan.careful_guidance,
            "checklist": checklist_status(plan, artifacts),
        },
        "evidence": [asdict(item) for item in artifacts],
        "timeline": [asdict(item) for item in build_timeline(artifacts)],
        "evidence_gaps": [asdict(gap) for gap in gaps],
        "packet": asdict(packet) if packet else None,
        "export_ready": ready,
        "export_reason": reason,
    }


def create_dispute(payload: Dict[str, Any]) -> Dict[str, Any]:
    dispute = ConsumerDispute(
        id=f"case_{uuid4().hex[:10]}",
        merchant_name=payload["merchant_name"].strip(),
        amount=int(round(float(payload["amount"]) * 100)),
        currency="USD",
        charge_date=payload["charge_date"],
        issuer_name=payload["issuer_name"].strip(),
        category=payload["category"],
        status="draft",
        user_summary=payload.get("user_summary", "").strip(),
        created_at=utc_now(),
    )
    save_dispute(dispute)
    return detail(dispute.id)


def add_evidence(dispute_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    get_dispute(dispute_id)
    evidence = EvidenceArtifact(
        id=f"ev_{uuid4().hex[:10]}",
        dispute_id=dispute_id,
        type=payload["type"],
        title=payload["title"].strip(),
        source=payload.get("source", "Manual entry").strip() or "Manual entry",
        occurred_at=payload["occurred_at"],
        summary=payload["summary"].strip(),
        relevance=payload.get("relevance", "relevant"),
    )
    save_evidence(evidence)
    return detail(dispute_id)


def generate_packet(dispute_id: str) -> Dict[str, Any]:
    dispute = get_dispute(dispute_id)
    artifacts = list_evidence(dispute_id)
    packet = generate_template_packet(dispute, artifacts)
    save_packet(packet)
    return detail(dispute_id)


def export_packet(dispute_id: str) -> str:
    data = detail(dispute_id)
    packet = data["packet"]
    if not packet:
        raise ValueError("Generate a dispute packet before export.")
    if not data["export_ready"]:
        raise ValueError(data["export_reason"])

    dispute = data["dispute"]
    claims = "\n".join(
        f"<li>{escape(claim['text'])}<br><small>Evidence: {escape(', '.join(claim['citation_evidence_ids']))}</small></li>"
        for claim in packet["claims"]
    )
    timeline = "\n".join(
        f"<li><strong>{escape(event['date'])}</strong> - {escape(event['title'])}<br>{escape(event['description'])}<br><small>Evidence: {escape(', '.join(event['evidence_ids']))}</small></li>"
        for event in packet["timeline"]
    )
    evidence_index = "\n".join(
        f"<li><strong>{escape(item['id'])}</strong>: {escape(item['title'])} ({escape(item['source'])})</li>"
        for item in data["evidence"]
    )
    next_steps = "\n".join(f"<li>{escape(step)}</li>" for step in packet["next_steps"])
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{escape(packet['title'])}</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #14213d; margin: 40px; line-height: 1.55; }}
    h1, h2 {{ color: #123047; }}
    small {{ color: #5f6f82; }}
    .box {{ border: 1px solid #d9e2ec; border-radius: 6px; padding: 14px; }}
  </style>
</head>
<body>
  <h1>{escape(packet['title'])}</h1>
  <div class="box">
    <p><strong>Merchant:</strong> {escape(dispute['merchant_name'])}</p>
    <p><strong>Amount:</strong> {escape(dispute['currency'])} {dispute['amount'] / 100:,.2f}</p>
    <p><strong>Charge date:</strong> {escape(dispute['charge_date'])}</p>
    <p><strong>Issuer:</strong> {escape(dispute['issuer_name'])}</p>
    <p><strong>Category:</strong> {escape(data['plan']['label'])}</p>
  </div>
  <h2>Suggested Bank Message</h2>
  <p>{escape(packet['suggested_bank_message'])}</p>
  <h2>Cited Claims</h2>
  <ol>{claims}</ol>
  <h2>Timeline</h2>
  <ol>{timeline}</ol>
  <h2>Evidence Index</h2>
  <ol>{evidence_index}</ol>
  <h2>Next Steps</h2>
  <ol>{next_steps}</ol>
  <p><small>{escape(packet['disclaimer'])}</small></p>
</body>
</html>"""

