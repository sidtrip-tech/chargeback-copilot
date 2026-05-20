from typing import Dict, Iterable, List

from .models import CategoryPlan, EvidenceArtifact, EvidenceGap, EvidenceRequirement


CATEGORY_PLANS: Dict[str, CategoryPlan] = {
    "unauthorized_charge": CategoryPlan(
        category="unauthorized_charge",
        label="I do not recognize this charge",
        description="The user believes the charge may be unauthorized or unfamiliar.",
        careful_guidance=(
            "Focus on what the consumer recognizes, whether they have a relationship with the merchant, "
            "and any issuer alerts or account-access details they can honestly provide."
        ),
        requirements=[
            EvidenceRequirement("transaction", "Transaction details from card statement", ["statement_transaction"]),
            EvidenceRequirement("merchant_relationship", "Whether the consumer recognizes the merchant", ["merchant_relationship"]),
            EvidenceRequirement("issuer_alert", "Bank alert or issuer communication", ["issuer_alert"], required=False),
            EvidenceRequirement("merchant_contact", "Merchant contact attempt or explanation", ["merchant_message"], required=False),
        ],
    ),
    "canceled_subscription": CategoryPlan(
        category="canceled_subscription",
        label="I canceled but was still charged",
        description="The user says they canceled a trial or subscription before or after a renewal charge.",
        careful_guidance=(
            "Reconstruct signup, renewal, cancellation, refund request, and merchant response dates. "
            "Do not claim cancellation happened before billing unless evidence supports it."
        ),
        requirements=[
            EvidenceRequirement("transaction", "Transaction details from card statement", ["statement_transaction"]),
            EvidenceRequirement("cancellation", "Cancellation confirmation or request", ["cancellation_confirmation"]),
            EvidenceRequirement("merchant_response", "Merchant support response", ["merchant_message"]),
            EvidenceRequirement("terms", "Subscription terms or renewal notice", ["terms_or_policy"], required=False),
        ],
    ),
    "not_received": CategoryPlan(
        category="not_received",
        label="I did not receive the item or service",
        description="The user paid for a product or service they say was not delivered.",
        careful_guidance=(
            "Show order details, expected delivery or service date, tracking or availability records, "
            "and merchant communications. Avoid implying fraud without evidence."
        ),
        requirements=[
            EvidenceRequirement("transaction", "Transaction or order confirmation", ["statement_transaction", "order_confirmation"]),
            EvidenceRequirement("delivery", "Tracking, delivery, or service availability record", ["delivery_status", "service_status"]),
            EvidenceRequirement("merchant_contact", "Merchant contact attempt", ["merchant_message"]),
        ],
    ),
    "refund_not_received": CategoryPlan(
        category="refund_not_received",
        label="I was promised a refund but did not receive it",
        description="The user says the merchant agreed to a refund that has not appeared.",
        careful_guidance=(
            "Anchor the case on the refund promise, return or cancellation proof, and elapsed time since the promise."
        ),
        requirements=[
            EvidenceRequirement("transaction", "Original transaction details", ["statement_transaction"]),
            EvidenceRequirement("refund_promise", "Refund promise or approval", ["refund_promise"]),
            EvidenceRequirement("return_or_cancel", "Return, cancellation, or eligibility proof", ["return_proof", "cancellation_confirmation"]),
            EvidenceRequirement("merchant_contact", "Merchant follow-up communication", ["merchant_message"], required=False),
        ],
    ),
}


def get_plan(category: str) -> CategoryPlan:
    try:
        return CATEGORY_PLANS[category]
    except KeyError as exc:
        raise ValueError(f"Unsupported dispute category: {category}") from exc


def checklist_status(plan: CategoryPlan, artifacts: Iterable[EvidenceArtifact]) -> List[dict]:
    available_types = {artifact.type for artifact in artifacts if artifact.relevance != "excluded"}
    return [
        {
            "key": requirement.key,
            "label": requirement.label,
            "required": requirement.required,
            "artifact_types": requirement.artifact_types,
            "satisfied": any(artifact_type in available_types for artifact_type in requirement.artifact_types),
        }
        for requirement in plan.requirements
    ]


def find_gaps(plan: CategoryPlan, artifacts: Iterable[EvidenceArtifact]) -> List[EvidenceGap]:
    gaps: List[EvidenceGap] = []
    for item in checklist_status(plan, artifacts):
        if item["satisfied"]:
            continue
        severity = "high" if item["required"] else "medium"
        gaps.append(
            EvidenceGap(
                requirement_key=item["key"],
                label=item["label"],
                severity=severity,
                explanation=f"This packet does not yet include evidence for: {item['label']}.",
                suggested_action=f"Add a receipt, screenshot, email, chat, or note that supports {item['label'].lower()}.",
            )
        )
    return gaps

