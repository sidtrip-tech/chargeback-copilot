from typing import Iterable, List

from .models import EvidenceArtifact, TimelineEvent


def build_timeline(artifacts: Iterable[EvidenceArtifact]) -> List[TimelineEvent]:
    active = [artifact for artifact in artifacts if artifact.relevance != "excluded"]
    ordered = sorted(active, key=lambda artifact: (artifact.occurred_at, artifact.id))
    return [
        TimelineEvent(
            id=f"tl_{artifact.id}",
            date=artifact.occurred_at,
            title=artifact.title,
            description=artifact.summary,
            evidence_ids=[artifact.id],
            support_status="evidence-backed",
        )
        for artifact in ordered
    ]


def evidence_by_id(artifacts: Iterable[EvidenceArtifact]) -> dict:
    return {artifact.id: artifact for artifact in artifacts}

