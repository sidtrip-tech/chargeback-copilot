import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chargeback_copilot.models import CitedClaim
from chargeback_copilot.dashboard import derived_status, evidence_progress, readiness_score
from chargeback_copilot.packets import generate_template_packet
from chargeback_copilot.planning import checklist_status, find_gaps, get_plan
from chargeback_copilot.seed_data import DISPUTES, EVIDENCE
from chargeback_copilot.store import get_outcome, init_db, save_outcome
from chargeback_copilot.models import OutcomeFeedback
from chargeback_copilot.timeline import build_timeline
from chargeback_copilot.validation import export_readiness, validate_claims


def dispute(dispute_id):
    return next(item for item in DISPUTES if item.id == dispute_id)


def evidence(dispute_id):
    return [item for item in EVIDENCE if item.dispute_id == dispute_id]


class ChargebackCopilotTests(unittest.TestCase):
    def test_category_plan_selects_subscription_requirements(self):
        plan = get_plan("canceled_subscription")
        labels = [requirement.label for requirement in plan.requirements]
        self.assertIn("Cancellation confirmation or request", labels)
        self.assertIn("Merchant support response", labels)

    def test_checklist_marks_missing_delivery_evidence(self):
        item = dispute("case_delivery_002")
        statuses = checklist_status(get_plan(item.category), evidence(item.id))
        by_key = {status["key"]: status for status in statuses}
        self.assertTrue(by_key["transaction"]["satisfied"])
        self.assertFalse(by_key["delivery"]["satisfied"])

    def test_gaps_include_high_priority_required_items(self):
        item = dispute("case_delivery_002")
        gaps = find_gaps(get_plan(item.category), evidence(item.id))
        self.assertTrue(any(gap.requirement_key == "delivery" and gap.severity == "high" for gap in gaps))

    def test_timeline_orders_events(self):
        events = build_timeline(reversed(evidence("case_sub_001")))
        dates = [event.date for event in events]
        self.assertEqual(dates, sorted(dates))

    def test_generated_packet_uses_valid_citations(self):
        item = dispute("case_sub_001")
        packet = generate_template_packet(item, evidence(item.id))
        self.assertGreater(len(packet.claims), 0)
        self.assertEqual(packet.validation_errors, [])
        source_ids = {artifact.id for artifact in evidence(item.id)}
        cited = {citation for claim in packet.claims for citation in claim.citation_evidence_ids}
        self.assertTrue(cited.issubset(source_ids))

    def test_validation_catches_uncited_and_invalid_claims(self):
        claims = [
            CitedClaim(id="claim_missing", text="No citation.", citation_evidence_ids=[]),
            CitedClaim(id="claim_invalid", text="Bad citation.", citation_evidence_ids=["ev_fake"]),
        ]
        errors = validate_claims(claims, evidence("case_sub_001"))
        self.assertEqual(len(errors), 2)
        self.assertIn("no evidence citation", errors[0])
        self.assertIn("invalid evidence citation", errors[1])

    def test_export_readiness_requires_packet_and_no_high_gaps(self):
        self.assertFalse(export_readiness([], False, False)[0])
        self.assertFalse(export_readiness([], True, True)[0])
        self.assertTrue(export_readiness([], False, True)[0])

    def test_readiness_score_and_progress(self):
        item = dispute("case_sub_001")
        statuses = checklist_status(get_plan(item.category), evidence(item.id))
        self.assertEqual(readiness_score(statuses), 100)
        self.assertEqual(evidence_progress(statuses), (3, 3))

    def test_derived_status_completed_vs_in_progress(self):
        complete = dispute("case_sub_001")
        complete_packet = generate_template_packet(complete, evidence(complete.id))
        complete_gaps = find_gaps(get_plan(complete.category), evidence(complete.id))
        self.assertEqual(derived_status(complete_packet, complete_gaps), "completed")

        incomplete = dispute("case_delivery_002")
        incomplete_packet = generate_template_packet(incomplete, evidence(incomplete.id))
        incomplete_gaps = find_gaps(get_plan(incomplete.category), evidence(incomplete.id))
        self.assertEqual(derived_status(incomplete_packet, incomplete_gaps), "in_progress")

    def test_outcome_feedback_save_and_read(self):
        init_db()
        feedback = OutcomeFeedback(
            dispute_id="case_sub_001",
            outcome="success",
            note="Issuer credited the account.",
            updated_at="2026-05-20T12:30:00Z",
        )
        save_outcome(feedback)
        stored = get_outcome("case_sub_001")
        self.assertEqual(stored.outcome, "success")
        self.assertEqual(stored.note, "Issuer credited the account.")


if __name__ == "__main__":
    unittest.main()
