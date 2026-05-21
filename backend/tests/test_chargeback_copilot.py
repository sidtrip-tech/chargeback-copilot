import sys
import unittest
from uuid import uuid4
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chargeback_copilot.models import CitedClaim
from chargeback_copilot import api
from chargeback_copilot.auth import DEMO_USER_ID
from chargeback_copilot.dashboard import derived_status, evidence_progress, readiness_score
from chargeback_copilot.packets import generate_template_packet
from chargeback_copilot.planning import checklist_status, find_gaps, get_plan
from chargeback_copilot.seed_data import DISPUTES, EVIDENCE
from chargeback_copilot.security import (
    OriginNotAllowed,
    PayloadTooLarge,
    RateLimitExceeded,
    check_json_body_size,
    check_origin,
    check_rate_limit,
    is_allowed_origin,
    parse_allowed_origins,
    reset_rate_limits,
)
from chargeback_copilot.scanning import EICAR_SIGNATURE, UnsafeUpload, scan_upload
from chargeback_copilot.uploads import clean_filename
from chargeback_copilot.store import (
    get_outcome,
    get_user_by_email,
    init_db,
    list_disputes,
    list_evidence_files,
    save_dispute,
    save_outcome,
)
from chargeback_copilot.models import ConsumerDispute, OutcomeFeedback
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

    def test_demo_login_creates_valid_session(self):
        init_db()
        login = api.demo_login()
        current = api.current_user(login["token"])
        self.assertEqual(current["id"], DEMO_USER_ID)
        self.assertEqual(current["email"], "demo@chargebackcopilot.local")

    def test_signup_and_login_create_user_session(self):
        init_db()
        email = f"test-{uuid4().hex[:8]}@example.com"
        signup = api.signup({"name": "Test User", "email": email, "password": "secure-test-password"})
        self.assertEqual(signup["user"]["email"], email)

        login = api.login({"email": email, "password": "secure-test-password"})
        current = api.current_user(login["token"])
        self.assertEqual(current["email"], email)

    def test_login_rejects_bad_password(self):
        init_db()
        email = f"bad-{uuid4().hex[:8]}@example.com"
        api.signup({"name": "Bad Password", "email": email, "password": "secure-test-password"})
        with self.assertRaises(PermissionError):
            api.login({"email": email, "password": "wrong-password"})

    def test_rate_limit_blocks_repeated_auth_attempts(self):
        reset_rate_limits()
        for index in range(10):
            check_rate_limit("127.0.0.1", "auth", now=float(index))
        with self.assertRaises(RateLimitExceeded):
            check_rate_limit("127.0.0.1", "auth", now=10.0)
        check_rate_limit("127.0.0.1", "auth", now=70.0)

    def test_json_body_size_limit(self):
        check_json_body_size(1024)
        with self.assertRaises(PayloadTooLarge):
            check_json_body_size(65537)

    def test_origin_allowlist(self):
        configured = parse_allowed_origins("https://app.example.com, http://localhost:8010/")
        self.assertTrue(is_allowed_origin("", "127.0.0.1:8010", "http", configured))
        self.assertTrue(is_allowed_origin("https://app.example.com", "service.onrender.com", "https", configured))
        self.assertTrue(is_allowed_origin("https://service.onrender.com", "service.onrender.com", "https", configured))
        self.assertFalse(is_allowed_origin("https://evil.example", "service.onrender.com", "https", configured))
        with self.assertRaises(OriginNotAllowed):
            check_origin("https://evil.example", "service.onrender.com", "https")

    def test_health_check(self):
        payload = api.health()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["service"], "chargeback-copilot")
        self.assertIn("timestamp", payload)

    def test_readiness_checks_database_and_storage(self):
        payload = api.readiness()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["checks"]["database"]["backend"], "sqlite")
        self.assertEqual(payload["checks"]["storage"]["backend"], "local")

    def test_disputes_are_scoped_by_owner(self):
        init_db()
        other_dispute = ConsumerDispute(
            id="case_other_owner",
            merchant_name="Other Merchant",
            amount=1000,
            currency="USD",
            charge_date="2026-05-20",
            issuer_name="Other Bank",
            category="not_received",
            status="draft",
            user_summary="Different owner case.",
            created_at="2026-05-20T13:00:00Z",
        )
        save_dispute(other_dispute, owner_id="user_other")

        demo_ids = {item.id for item in list_disputes(DEMO_USER_ID)}
        other_ids = {item.id for item in list_disputes("user_other")}
        self.assertNotIn(other_dispute.id, demo_ids)
        self.assertIn(other_dispute.id, other_ids)
        with self.assertRaises(KeyError):
            api.detail(other_dispute.id, DEMO_USER_ID)

    def test_account_export_and_delete(self):
        init_db()
        email = f"delete-{uuid4().hex[:8]}@example.com"
        signup = api.signup({"name": "Delete Me", "email": email, "password": "secure-test-password"})
        user_id = signup["user"]["id"]
        api.create_dispute(
            {
                "merchant_name": "Delete Test Merchant",
                "amount": "10.00",
                "charge_date": "2026-05-21",
                "issuer_name": "Test Bank",
                "category": "not_received",
                "user_summary": "Delete account test.",
            },
            user_id,
        )

        exported = api.export_account_data(user_id)
        self.assertEqual(exported["user"]["email"], email)
        self.assertEqual(len(exported["disputes"]), 1)
        self.assertNotIn("password_hash", exported["user"])

        api.delete_account_data(user_id, {"confirmation": "DELETE"})
        self.assertIsNone(get_user_by_email(email))
        self.assertEqual(list_disputes(user_id), [])

    def test_demo_account_cannot_be_deleted(self):
        init_db()
        with self.assertRaises(ValueError):
            api.delete_account_data(DEMO_USER_ID, {"confirmation": "DELETE"})

    def test_evidence_file_upload_creates_metadata(self):
        init_db()
        api.add_evidence_upload(
            "case_delivery_002",
            {
                "type": "delivery_status",
                "title": "Tracking screenshot",
                "source": "Carrier website",
                "occurred_at": "2026-05-21",
                "summary": "Tracking page shows no delivery scan.",
            },
            {
                "filename": "tracking.txt",
                "content_type": "text/plain",
                "data": b"No delivery scan",
            },
            DEMO_USER_ID,
        )
        files = list_evidence_files(DEMO_USER_ID, "case_delivery_002")
        self.assertTrue(any(file.original_filename == "tracking.txt" for file in files))
        jobs = api.job_status(DEMO_USER_ID)["jobs"]
        self.assertTrue(any(job["job_type"] == "evidence_file.post_upload_processing" for job in jobs))
        completed = api.run_jobs()["completed"]
        self.assertTrue(any(job["status"] == "completed" for job in completed))
        exported = api.export_account_data(DEMO_USER_ID)
        self.assertIn("evidence_files", exported)

    def test_evidence_file_download_and_delete_are_owner_checked(self):
        init_db()
        detail = api.add_evidence_upload(
            "case_delivery_002",
            {
                "type": "delivery_status",
                "title": "Carrier note",
                "source": "Carrier website",
                "occurred_at": "2026-05-21",
                "summary": "Carrier says the package is still in transit.",
            },
            {
                "filename": "carrier-note.txt",
                "content_type": "text/plain",
                "data": b"Still in transit",
            },
            DEMO_USER_ID,
        )
        file_id = next(file["id"] for file in detail["evidence_files"] if file["original_filename"] == "carrier-note.txt")

        downloaded = api.download_evidence_file(file_id, DEMO_USER_ID)
        self.assertEqual(downloaded["data"], b"Still in transit")
        with self.assertRaises(ValueError):
            api.download_evidence_file(file_id, "other_user")

        api.delete_uploaded_evidence_file(file_id, DEMO_USER_ID)
        self.assertFalse(any(file.id == file_id for file in list_evidence_files(DEMO_USER_ID, "case_delivery_002")))

    def test_upload_filename_cleanup(self):
        self.assertEqual(clean_filename("../bad name!!.pdf"), "bad name_.pdf")
        self.assertEqual(clean_filename("   "), "evidence-upload")

    def test_basic_upload_scanner_can_block_eicar_signature(self):
        import chargeback_copilot.scanning as scanning

        original_enabled = scanning.VIRUS_SCAN_ENABLED
        try:
            scanning.VIRUS_SCAN_ENABLED = True
            self.assertEqual(scan_upload(b"ordinary receipt text"), "clean")
            with self.assertRaises(UnsafeUpload):
                scan_upload(b"prefix " + EICAR_SIGNATURE + b" suffix")
        finally:
            scanning.VIRUS_SCAN_ENABLED = original_enabled


if __name__ == "__main__":
    unittest.main()
