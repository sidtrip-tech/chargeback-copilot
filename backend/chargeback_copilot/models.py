from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ConsumerDispute:
    id: str
    merchant_name: str
    amount: int
    currency: str
    charge_date: str
    issuer_name: str
    category: str
    status: str
    user_summary: str
    created_at: str


@dataclass(frozen=True)
class EvidenceArtifact:
    id: str
    dispute_id: str
    type: str
    title: str
    source: str
    occurred_at: str
    summary: str
    relevance: str = "relevant"
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceRequirement:
    key: str
    label: str
    artifact_types: List[str]
    required: bool = True


@dataclass(frozen=True)
class EvidenceGap:
    requirement_key: str
    label: str
    severity: str
    explanation: str
    suggested_action: str


@dataclass(frozen=True)
class CategoryPlan:
    category: str
    label: str
    description: str
    careful_guidance: str
    requirements: List[EvidenceRequirement]


@dataclass(frozen=True)
class TimelineEvent:
    id: str
    date: str
    title: str
    description: str
    evidence_ids: List[str]
    support_status: str


@dataclass(frozen=True)
class CitedClaim:
    id: str
    text: str
    citation_evidence_ids: List[str]
    support_status: str = "supported"


@dataclass(frozen=True)
class Packet:
    id: str
    dispute_id: str
    title: str
    summary: str
    suggested_bank_message: str
    claims: List[CitedClaim]
    timeline: List[TimelineEvent]
    evidence_gaps: List[EvidenceGap]
    next_steps: List[str]
    validation_errors: List[str]
    status: str
    created_at: str
    disclaimer: str
    mode: str = "template"
    fallback_used: bool = False
    fallback_reason: Optional[str] = None


@dataclass(frozen=True)
class OutcomeFeedback:
    dispute_id: str
    outcome: str
    note: str
    updated_at: str
