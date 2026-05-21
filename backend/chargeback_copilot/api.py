from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Dict, Optional
from uuid import uuid4

from .auth import DEMO_USER_ID
from .dashboard import derived_status, evidence_progress, next_step_prompts, readiness_score
from .models import AuditLog, ConsumerDispute, EvidenceArtifact, OutcomeFeedback
from .packets import generate_template_packet
from .planning import checklist_status, find_gaps, get_plan
from .store import (
    create_session,
    delete_session,
    get_dispute,
    get_latest_packet,
    get_outcome,
    get_session_user,
    get_user,
    init_db,
    list_audit_logs,
    list_disputes,
    list_evidence,
    save_audit_log,
    save_dispute,
    save_evidence,
    save_outcome,
    save_packet,
)
from .timeline import build_timeline
from .validation import export_readiness


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _session_expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=14)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def boot() -> None:
    init_db()


def health() -> Dict[str, Any]:
    init_db()
    return {
        "ok": True,
        "service": "chargeback-copilot",
        "timestamp": utc_now(),
    }


def demo_login() -> Dict[str, Any]:
    user = get_user(DEMO_USER_ID)
    token = create_session(user.id, utc_now(), _session_expiry())
    return {
        "token": token,
        "user": {"id": user.id, "email": user.email, "name": user.name},
    }


def current_user(token: str) -> Dict[str, Any]:
    user = get_session_user(token, utc_now())
    if not user:
        raise PermissionError("Sign in to continue.")
    return {"id": user.id, "email": user.email, "name": user.name}


def logout(token: str) -> Dict[str, Any]:
    if token:
        delete_session(token)
    return {"ok": True}


def _audit(user_id: str, action: str, entity_type: str, entity_id: str, metadata: Optional[Dict[str, str]] = None) -> None:
    save_audit_log(
        AuditLog(
            id=f"audit_{uuid4().hex[:12]}",
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            created_at=utc_now(),
            metadata=metadata or {},
        )
    )


def list_cases(user_id: str = DEMO_USER_ID) -> Dict[str, Any]:
    disputes = []
    summary = {
        "total": 0,
        "in_progress": 0,
        "completed": 0,
        "high_gap": 0,
        "reported_success": 0,
        "reported_failure": 0,
    }
    for dispute in list_disputes(user_id):
        details = detail(dispute.id, user_id)
        summary["total"] += 1
        summary[details["derived_status"]] += 1
        if any(gap["severity"] == "high" for gap in details["evidence_gaps"]):
            summary["high_gap"] += 1
        outcome = details["outcome_feedback"]
        if outcome and outcome["outcome"] == "success":
            summary["reported_success"] += 1
        if outcome and outcome["outcome"] == "failure":
            summary["reported_failure"] += 1
        disputes.append(
            {
                **details["dispute"],
                "plan_label": details["plan"]["label"],
                "derived_status": details["derived_status"],
                "readiness_score": details["readiness_score"],
                "export_ready": details["export_ready"],
                "outcome_feedback": outcome,
                "high_gap_count": sum(1 for gap in details["evidence_gaps"] if gap["severity"] == "high"),
            }
        )
    return {"disputes": disputes, "summary": summary}


def detail(dispute_id: str, user_id: str = DEMO_USER_ID) -> Dict[str, Any]:
    dispute = get_dispute(dispute_id, user_id)
    artifacts = list_evidence(dispute_id, user_id)
    plan = get_plan(dispute.category)
    checklist = checklist_status(plan, artifacts)
    gaps = find_gaps(plan, artifacts)
    packet = get_latest_packet(dispute_id, user_id)
    outcome = get_outcome(dispute_id, user_id)
    status = derived_status(packet, gaps)
    satisfied, required = evidence_progress(checklist)
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
            "checklist": checklist,
        },
        "evidence": [asdict(item) for item in artifacts],
        "timeline": [asdict(item) for item in build_timeline(artifacts)],
        "evidence_gaps": [asdict(gap) for gap in gaps],
        "packet": asdict(packet) if packet else None,
        "outcome_feedback": asdict(outcome) if outcome else None,
        "derived_status": status,
        "readiness_score": readiness_score(checklist),
        "evidence_progress": {"satisfied_required": satisfied, "total_required": required},
        "next_steps": next_step_prompts(packet, gaps),
        "export_ready": ready,
        "export_reason": reason,
    }


def create_dispute(payload: Dict[str, Any], user_id: str = DEMO_USER_ID) -> Dict[str, Any]:
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
    save_dispute(dispute, user_id)
    _audit(user_id, "dispute.created", "dispute", dispute.id, {"category": dispute.category})
    return detail(dispute.id, user_id)


def add_evidence(dispute_id: str, payload: Dict[str, Any], user_id: str = DEMO_USER_ID) -> Dict[str, Any]:
    get_dispute(dispute_id, user_id)
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
    save_evidence(evidence, user_id)
    _audit(user_id, "evidence.created", "evidence", evidence.id, {"dispute_id": dispute_id, "type": evidence.type})
    return detail(dispute_id, user_id)


def generate_packet(dispute_id: str, user_id: str = DEMO_USER_ID) -> Dict[str, Any]:
    dispute = get_dispute(dispute_id, user_id)
    artifacts = list_evidence(dispute_id, user_id)
    packet = generate_template_packet(dispute, artifacts)
    save_packet(packet, user_id)
    _audit(user_id, "packet.generated", "packet", packet.id, {"dispute_id": dispute_id, "mode": packet.mode})
    return detail(dispute_id, user_id)


def save_outcome_feedback(dispute_id: str, payload: Dict[str, Any], user_id: str = DEMO_USER_ID) -> Dict[str, Any]:
    current = detail(dispute_id, user_id)
    if current["derived_status"] != "completed":
        raise ValueError("Outcome feedback is available only for completed packets.")
    outcome = payload.get("outcome")
    if outcome not in {"success", "failure", "pending"}:
        raise ValueError("Outcome must be success, failure, or pending.")
    save_outcome(
        OutcomeFeedback(
            dispute_id=dispute_id,
            outcome=outcome,
            note=payload.get("note", "").strip(),
            updated_at=utc_now(),
        ),
        user_id,
    )
    _audit(user_id, "outcome.updated", "outcome", dispute_id, {"outcome": outcome})
    return detail(dispute_id, user_id)


def export_packet(dispute_id: str, user_id: str = DEMO_USER_ID) -> str:
    data = detail(dispute_id, user_id)
    packet = data["packet"]
    if not packet:
        raise ValueError("Generate a dispute packet before export.")
    if not data["export_ready"]:
        raise ValueError(data["export_reason"])
    _audit(user_id, "packet.exported", "dispute", dispute_id, {"format": "html"})

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


def audit_log(user_id: str) -> Dict[str, Any]:
    return {"audit_logs": [asdict(entry) for entry in list_audit_logs(user_id)]}
