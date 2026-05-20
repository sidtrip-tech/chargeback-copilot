from typing import Iterable, List, Tuple

from .models import CitedClaim, EvidenceArtifact


def validate_claims(claims: Iterable[CitedClaim], artifacts: Iterable[EvidenceArtifact]) -> List[str]:
    valid_ids = {artifact.id for artifact in artifacts if artifact.relevance != "excluded"}
    errors: List[str] = []
    for claim in claims:
        if not claim.citation_evidence_ids:
            errors.append(f"{claim.id}: claim has no evidence citation")
            continue
        invalid = [citation for citation in claim.citation_evidence_ids if citation not in valid_ids]
        if invalid:
            errors.append(f"{claim.id}: invalid evidence citation(s): {', '.join(invalid)}")
    return errors


def export_readiness(validation_errors: Iterable[str], has_high_gaps: bool, has_packet: bool) -> Tuple[bool, str]:
    errors = list(validation_errors)
    if not has_packet:
        return False, "Generate a dispute packet before export."
    if errors:
        return False, "The packet includes unsupported or uncited claims."
    if has_high_gaps:
        return False, "Important evidence is missing. Add evidence or keep this packet as a draft."
    return True, "Ready to export."

