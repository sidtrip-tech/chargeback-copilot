from datetime import datetime, timezone
from typing import List
from uuid import uuid4

from .models import CitedClaim, ConsumerDispute, EvidenceArtifact, Packet
from .planning import find_gaps, get_plan
from .timeline import build_timeline
from .validation import validate_claims


DISCLAIMER = (
    "Chargeback Copilot helps organize dispute information. It is not legal, financial, "
    "or banking advice and does not guarantee a refund or dispute outcome."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def dollars(cents: int, currency: str) -> str:
    return f"{currency} {cents / 100:,.2f}"


def _first_artifact(artifacts: List[EvidenceArtifact], *types: str):
    for artifact in artifacts:
        if artifact.type in types and artifact.relevance != "excluded":
            return artifact
    return None


def _claim(claim_id: str, text: str, evidence: EvidenceArtifact) -> CitedClaim:
    return CitedClaim(id=claim_id, text=text, citation_evidence_ids=[evidence.id])


def generate_template_packet(dispute: ConsumerDispute, artifacts: List[EvidenceArtifact]) -> Packet:
    plan = get_plan(dispute.category)
    gaps = find_gaps(plan, artifacts)
    timeline = build_timeline(artifacts)
    claims: List[CitedClaim] = []

    transaction = _first_artifact(artifacts, "statement_transaction", "order_confirmation")
    if transaction:
        claims.append(
            _claim(
                "claim_transaction",
                f"The packet concerns a {dollars(dispute.amount, dispute.currency)} charge from {dispute.merchant_name} dated {dispute.charge_date}.",
                transaction,
            )
        )

    if dispute.category == "canceled_subscription":
        cancellation = _first_artifact(artifacts, "cancellation_confirmation")
        merchant_response = _first_artifact(artifacts, "merchant_message")
        terms = _first_artifact(artifacts, "terms_or_policy")
        if cancellation:
            claims.append(_claim("claim_cancellation", cancellation.summary, cancellation))
        if merchant_response:
            claims.append(_claim("claim_merchant_response", merchant_response.summary, merchant_response))
        if terms:
            claims.append(_claim("claim_terms", terms.summary, terms))
    elif dispute.category == "not_received":
        order = _first_artifact(artifacts, "order_confirmation")
        delivery = _first_artifact(artifacts, "delivery_status", "service_status")
        merchant_message = _first_artifact(artifacts, "merchant_message")
        if order:
            claims.append(_claim("claim_order", order.summary, order))
        if delivery:
            claims.append(_claim("claim_delivery_status", delivery.summary, delivery))
        if merchant_message:
            claims.append(_claim("claim_merchant_contact", merchant_message.summary, merchant_message))
    elif dispute.category == "refund_not_received":
        promise = _first_artifact(artifacts, "refund_promise")
        return_proof = _first_artifact(artifacts, "return_proof", "cancellation_confirmation")
        merchant_message = _first_artifact(artifacts, "merchant_message")
        if promise:
            claims.append(_claim("claim_refund_promise", promise.summary, promise))
        if return_proof:
            claims.append(_claim("claim_return_or_cancel", return_proof.summary, return_proof))
        if merchant_message:
            claims.append(_claim("claim_merchant_followup", merchant_message.summary, merchant_message))
    elif dispute.category == "unauthorized_charge":
        relationship = _first_artifact(artifacts, "merchant_relationship")
        issuer_alert = _first_artifact(artifacts, "issuer_alert")
        merchant_message = _first_artifact(artifacts, "merchant_message")
        if relationship:
            claims.append(_claim("claim_merchant_relationship", relationship.summary, relationship))
        if issuer_alert:
            claims.append(_claim("claim_issuer_alert", issuer_alert.summary, issuer_alert))
        if merchant_message:
            claims.append(_claim("claim_merchant_contact", merchant_message.summary, merchant_message))

    summary = (
        f"This packet helps prepare a {plan.label.lower()} dispute for {dispute.issuer_name}. "
        f"It includes {len(claims)} cited claim(s), {len(timeline)} timeline event(s), and {len(gaps)} evidence gap(s)."
    )
    suggested_bank_message = (
        f"I am disputing the {dollars(dispute.amount, dispute.currency)} charge from {dispute.merchant_name} "
        f"on {dispute.charge_date}. Based on the attached evidence, I believe this dispute should be reviewed as: "
        f"{plan.label}. I have included a timeline, supporting evidence, and notes about any missing information."
    )
    next_steps = [
        "Review each claim and remove anything that does not match your records.",
        "Add evidence for any high-priority gaps before submitting to your issuer.",
        "Contact the merchant first if your issuer asks for a merchant-resolution attempt.",
        "Submit the final packet through your bank or card issuer's official dispute channel.",
    ]
    validation_errors = validate_claims(claims, artifacts)
    has_high_gaps = any(gap.severity == "high" for gap in gaps)
    status = "blocked" if validation_errors or has_high_gaps else "ready"

    return Packet(
        id=f"pkt_{uuid4().hex[:12]}",
        dispute_id=dispute.id,
        title=f"Dispute Packet: {dispute.merchant_name}",
        summary=summary,
        suggested_bank_message=suggested_bank_message,
        claims=claims,
        timeline=timeline,
        evidence_gaps=gaps,
        next_steps=next_steps,
        validation_errors=validation_errors,
        status=status,
        created_at=utc_now(),
        disclaimer=DISCLAIMER,
    )

