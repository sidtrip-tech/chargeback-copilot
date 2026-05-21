from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Dict, Optional
from uuid import uuid4

from .auth import DEMO_USER_ID, hash_password, new_auth_token, verify_password
from .dashboard import derived_status, evidence_progress, next_step_prompts, readiness_score
from .emailer import email_delivery_configured, email_health, send_password_reset_email, send_test_email, send_verification_email
from .jobs import enqueue_job, list_jobs, run_once
from .models import AuthToken, AuditLog, ConsumerDispute, EvidenceArtifact, OutcomeFeedback, User
from .packets import generate_template_packet
from .planning import checklist_status, find_gaps, get_plan
from .store import (
    create_session,
    delete_account,
    delete_evidence_file,
    delete_session,
    get_evidence_file,
    get_auth_token,
    get_dispute,
    get_latest_packet,
    get_outcome,
    get_session_user,
    get_user,
    get_user_by_email,
    database_health,
    init_db,
    list_audit_logs,
    list_disputes,
    list_evidence,
    list_evidence_files,
    list_outcomes,
    list_packets,
    mark_auth_token_used,
    mark_email_verified,
    save_audit_log,
    save_auth_token,
    save_dispute,
    save_evidence,
    save_evidence_file,
    save_outcome,
    save_packet,
    save_user,
    update_user_password,
)
from .timeline import build_timeline
from .uploads import read_evidence_file, remove_evidence_file, storage_healthcheck, store_evidence_file
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


def readiness() -> Dict[str, Any]:
    init_db()
    checks = {
        "database": database_health(),
        "storage": storage_healthcheck(),
        "email": email_health(),
    }
    return {
        "ok": all(item["ok"] for item in checks.values()),
        "service": "chargeback-copilot",
        "timestamp": utc_now(),
        "checks": checks,
    }


def run_jobs() -> Dict[str, Any]:
    completed = run_once(utc_now())
    return {"completed": [asdict(job) for job in completed]}


def _public_user(user: User) -> Dict[str, Any]:
    return {"id": user.id, "email": user.email, "name": user.name, "email_verified": bool(user.email_verified_at)}


def _auth_response(user: User) -> Dict[str, Any]:
    token = create_session(user.id, utc_now(), _session_expiry())
    return {"token": token, "user": _public_user(user)}


def _clean_email(email: str) -> str:
    return email.strip().lower()


def _token_expiry(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _create_auth_token(user_id: str, purpose: str, hours: int) -> AuthToken:
    auth_token = AuthToken(
        token=new_auth_token(),
        user_id=user_id,
        purpose=purpose,
        created_at=utc_now(),
        expires_at=_token_expiry(hours),
    )
    save_auth_token(auth_token)
    return auth_token


def signup(payload: Dict[str, Any]) -> Dict[str, Any]:
    email = _clean_email(payload.get("email", ""))
    name = payload.get("name", "").strip()
    password = payload.get("password", "")
    if "@" not in email or "." not in email:
        raise ValueError("Enter a valid email address.")
    if len(name) < 2:
        raise ValueError("Enter your name.")
    if len(password) < 8:
        raise ValueError("Use a password with at least 8 characters.")
    if get_user_by_email(email):
        raise ValueError("An account already exists for this email.")

    user = User(
        id=f"user_{uuid4().hex[:12]}",
        email=email,
        name=name,
        password_hash=hash_password(password),
        created_at=utc_now(),
    )
    save_user(user)
    verification = _create_auth_token(user.id, "email_verification", 48)
    email_sent = send_verification_email(user.email, verification.token)
    _audit(user.id, "account.created", "user", user.id, {"auth_provider": "local"})
    payload = _auth_response(user)
    payload["email_verification_sent"] = email_sent
    payload["email_delivery_configured"] = email_delivery_configured()
    return payload


def login(payload: Dict[str, Any]) -> Dict[str, Any]:
    email = _clean_email(payload.get("email", ""))
    password = payload.get("password", "")
    user = get_user_by_email(email)
    if not user or not verify_password(password, user.password_hash):
        raise PermissionError("Email or password is incorrect.")
    return _auth_response(user)


def demo_login() -> Dict[str, Any]:
    user = get_user(DEMO_USER_ID)
    return _auth_response(user)


def request_email_verification(user_id: str) -> Dict[str, Any]:
    user = get_user(user_id)
    if user.email_verified_at:
        return {"ok": True, "email_verified": True, "email_sent": False}
    token = _create_auth_token(user.id, "email_verification", 48)
    email_sent = send_verification_email(user.email, token.token)
    _audit(user.id, "email_verification.requested", "user", user.id, {"email_sent": str(email_sent)})
    return {"ok": True, "email_verified": False, "email_sent": email_sent, "email_delivery_configured": email_delivery_configured()}


def send_account_test_email(user_id: str) -> Dict[str, Any]:
    user = get_user(user_id)
    email_sent = send_test_email(user.email)
    _audit(user.id, "email.test_requested", "user", user.id, {"email_sent": str(email_sent)})
    return {"ok": True, "email_sent": email_sent, "email_delivery_configured": email_delivery_configured()}


def verify_email(payload: Dict[str, Any]) -> Dict[str, Any]:
    token = payload.get("token", "").strip()
    auth_token = get_auth_token(token, "email_verification", utc_now())
    if not auth_token:
        raise ValueError("Verification link is invalid or expired.")
    verified_at = utc_now()
    mark_email_verified(auth_token.user_id, verified_at)
    mark_auth_token_used(token, verified_at)
    _audit(auth_token.user_id, "email.verified", "user", auth_token.user_id, {})
    return {"ok": True, "email_verified": True}


def request_password_reset(payload: Dict[str, Any]) -> Dict[str, Any]:
    email = _clean_email(payload.get("email", ""))
    user = get_user_by_email(email)
    if user:
        token = _create_auth_token(user.id, "password_reset", 2)
        email_sent = send_password_reset_email(user.email, token.token)
        _audit(user.id, "password_reset.requested", "user", user.id, {"email_sent": str(email_sent)})
    return {"ok": True, "message": "If an account exists for that email, reset instructions will be sent.", "email_delivery_configured": email_delivery_configured()}


def reset_password(payload: Dict[str, Any]) -> Dict[str, Any]:
    token = payload.get("token", "").strip()
    password = payload.get("password", "")
    if len(password) < 8:
        raise ValueError("Use a password with at least 8 characters.")
    auth_token = get_auth_token(token, "password_reset", utc_now())
    if not auth_token:
        raise ValueError("Reset link is invalid or expired.")
    used_at = utc_now()
    update_user_password(auth_token.user_id, hash_password(password))
    mark_auth_token_used(token, used_at)
    _audit(auth_token.user_id, "password_reset.completed", "user", auth_token.user_id, {})
    return {"ok": True}


def current_user(token: str) -> Dict[str, Any]:
    user = get_session_user(token, utc_now())
    if not user:
        raise PermissionError("Sign in to continue.")
    return _public_user(user)


def logout(token: str) -> Dict[str, Any]:
    if token:
        delete_session(token)
    return {"ok": True}


def export_account_data(user_id: str) -> Dict[str, Any]:
    user = get_user(user_id)
    disputes = list_disputes(user_id)
    evidence = []
    for dispute in disputes:
        evidence.extend(list_evidence(dispute.id, user_id))
    evidence_files = list_evidence_files(user_id)
    packets = list_packets(user_id)
    outcomes = list_outcomes(user_id)
    audit_logs = list_audit_logs(user_id)
    _audit(user_id, "account.exported", "user", user_id)
    return {
        "exported_at": utc_now(),
        "user": _public_user(user),
        "disputes": [asdict(item) for item in disputes],
        "evidence": [asdict(item) for item in evidence],
        "evidence_files": [asdict(item) for item in evidence_files],
        "packets": [asdict(item) for item in packets],
        "outcomes": [asdict(item) for item in outcomes],
        "audit_logs": [asdict(item) for item in audit_logs],
    }


def delete_account_data(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if user_id == DEMO_USER_ID:
        raise ValueError("The shared demo account cannot be deleted.")
    confirmation = payload.get("confirmation", "")
    if confirmation != "DELETE":
        raise ValueError("Type DELETE to confirm account deletion.")
    _audit(user_id, "account.deleted", "user", user_id)
    delete_account(user_id)
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
    files = list_evidence_files(user_id, dispute_id)
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
        "evidence_files": [asdict(item) for item in files],
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


def add_evidence_upload(dispute_id: str, fields: Dict[str, str], file_payload: Dict[str, Any], user_id: str = DEMO_USER_ID) -> Dict[str, Any]:
    get_dispute(dispute_id, user_id)
    evidence_id = f"ev_{uuid4().hex[:10]}"
    created_at = utc_now()
    evidence = EvidenceArtifact(
        id=evidence_id,
        dispute_id=dispute_id,
        type=fields["type"],
        title=fields["title"].strip(),
        source=fields.get("source", "Uploaded file").strip() or "Uploaded file",
        occurred_at=fields["occurred_at"],
        summary=fields["summary"].strip(),
        relevance=fields.get("relevance", "relevant"),
        metadata={"input_mode": "file_upload"},
    )
    stored_file = store_evidence_file(
        evidence_id=evidence_id,
        dispute_id=dispute_id,
        owner_id=user_id,
        filename=file_payload["filename"],
        content_type=file_payload["content_type"],
        data=file_payload["data"],
        created_at=created_at,
    )
    save_evidence(evidence, user_id)
    save_evidence_file(stored_file)
    enqueue_job(
        user_id,
        "evidence_file.post_upload_processing",
        {"file_id": stored_file.id, "evidence_id": evidence_id, "dispute_id": dispute_id},
        utc_now(),
    )
    _audit(
        user_id,
        "evidence_file.uploaded",
        "evidence_file",
        stored_file.id,
        {"dispute_id": dispute_id, "content_type": stored_file.content_type, "size_bytes": str(stored_file.size_bytes)},
    )
    return detail(dispute_id, user_id)


def download_evidence_file(file_id: str, user_id: str = DEMO_USER_ID) -> Dict[str, Any]:
    file = get_evidence_file(user_id, file_id)
    if not file:
        raise ValueError("Evidence file not found.")
    return {"file": asdict(file), "data": read_evidence_file(file)}


def delete_uploaded_evidence_file(file_id: str, user_id: str = DEMO_USER_ID) -> Dict[str, Any]:
    file = get_evidence_file(user_id, file_id)
    if not file:
        raise ValueError("Evidence file not found.")
    remove_evidence_file(file)
    delete_evidence_file(user_id, file_id, utc_now())
    _audit(user_id, "evidence_file.deleted", "evidence_file", file.id, {"dispute_id": file.dispute_id})
    return detail(file.dispute_id, user_id)


def job_status(user_id: str) -> Dict[str, Any]:
    return list_jobs(user_id)


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
    file_index = "\n".join(
        f"<li><strong>{escape(item['id'])}</strong>: {escape(item['original_filename'])} ({escape(item['content_type'])}, {item['size_bytes'] / 1024:,.1f} KB)<br><small>Evidence: {escape(item['evidence_id'])}; Scan: {escape(item['scan_status'])}</small></li>"
        for item in data.get("evidence_files", [])
    )
    next_steps = "\n".join(f"<li>{escape(step)}</li>" for step in packet["next_steps"])
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(packet['title'])}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ font-family: Arial, sans-serif; color: #14213d; margin: 0; line-height: 1.55; background: #eef3f8; }}
    main {{ max-width: 840px; margin: 0 auto; background: white; min-height: 100vh; padding: 44px; }}
    h1, h2 {{ color: #123047; line-height: 1.2; }}
    h1 {{ margin-top: 0; }}
    h2 {{ border-top: 1px solid #d9e2ec; padding-top: 18px; margin-top: 28px; page-break-after: avoid; }}
    li {{ margin-bottom: 10px; }}
    small {{ color: #5f6f82; }}
    .box {{ border: 1px solid #d9e2ec; border-radius: 6px; padding: 14px; }}
    .toolbar {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 28px; padding: 12px 14px; border: 1px solid #cfe0ea; background: #f7fbfe; border-radius: 6px; }}
    .toolbar p {{ margin: 0; color: #526177; font-size: 13px; }}
    button {{ border: 1px solid #0b7285; border-radius: 6px; background: #0b7285; color: white; padding: 8px 12px; cursor: pointer; }}
    .section {{ page-break-inside: avoid; }}
    .disclaimer {{ margin-top: 28px; border-top: 1px solid #d9e2ec; padding-top: 12px; }}
    @page {{ margin: 0.6in; }}
    @media print {{
      body {{ background: white; }}
      main {{ max-width: none; padding: 0; }}
      .toolbar {{ display: none; }}
      a {{ color: inherit; text-decoration: none; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="toolbar">
      <p>PDF-ready export. Use your browser print dialog and choose Save as PDF.</p>
      <button onclick="window.print()">Save as PDF</button>
    </div>
    <h1>{escape(packet['title'])}</h1>
    <div class="box section">
      <p><strong>Merchant:</strong> {escape(dispute['merchant_name'])}</p>
      <p><strong>Amount:</strong> {escape(dispute['currency'])} {dispute['amount'] / 100:,.2f}</p>
      <p><strong>Charge date:</strong> {escape(dispute['charge_date'])}</p>
      <p><strong>Issuer:</strong> {escape(dispute['issuer_name'])}</p>
      <p><strong>Category:</strong> {escape(data['plan']['label'])}</p>
    </div>
    <section class="section">
      <h2>Suggested Bank Message</h2>
      <p>{escape(packet['suggested_bank_message'])}</p>
    </section>
    <section>
      <h2>Cited Claims</h2>
      <ol>{claims}</ol>
    </section>
    <section>
      <h2>Timeline</h2>
      <ol>{timeline}</ol>
    </section>
    <section>
      <h2>Evidence Index</h2>
      <ol>{evidence_index}</ol>
    </section>
    <section>
      <h2>Uploaded File Index</h2>
      <ol>{file_index or "<li>No uploaded files attached.</li>"}</ol>
    </section>
    <section>
      <h2>Next Steps</h2>
      <ol>{next_steps}</ol>
    </section>
    <p class="disclaimer"><small>{escape(packet['disclaimer'])}</small></p>
  </main>
</body>
</html>"""


def audit_log(user_id: str) -> Dict[str, Any]:
    return {"audit_logs": [asdict(entry) for entry in list_audit_logs(user_id)]}
