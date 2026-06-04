import sys
import unittest
import os
from dataclasses import replace
from uuid import uuid4
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chargeback_copilot.models import BackgroundJob, CitedClaim
from chargeback_copilot import api
from chargeback_copilot import ai
from chargeback_copilot import jobs
from server import Handler
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
    get_background_job,
    get_outcome,
    get_user_by_email,
    init_db,
    list_audit_logs,
    list_disputes,
    list_evidence_files,
    save_background_job,
    save_evidence,
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

    def test_live_ai_generation_falls_back_when_unconfigured(self):
        original_enabled = ai.AI_ENABLED
        original_key = ai.OPENAI_API_KEY
        try:
            ai.AI_ENABLED = False
            ai.OPENAI_API_KEY = ""
            init_db()
            dispute_id = f"case_{uuid4().hex}"
            save_dispute(replace(dispute("case_sub_001"), id=dispute_id), DEMO_USER_ID)
            for artifact in evidence("case_sub_001"):
                save_evidence(
                    replace(artifact, id=f"{artifact.id}_{uuid4().hex[:8]}", dispute_id=dispute_id),
                    DEMO_USER_ID,
                )
            detail = api.generate_packet(dispute_id, user_id=DEMO_USER_ID, mode="live_ai")
            self.assertTrue(detail["packet"]["fallback_used"])
            self.assertEqual(detail["packet"]["mode"], "live_ai")
            self.assertIn("not configured", detail["packet"]["fallback_reason"])
            self.assertEqual(detail["packet"]["generation_metadata"]["generator"], "template")
            generated = next(
                entry
                for entry in list_audit_logs(DEMO_USER_ID)
                if entry.action == "packet.generated" and entry.metadata.get("dispute_id") == dispute_id
            )
            self.assertEqual(generated.metadata["requested_mode"], "live_ai")
            self.assertEqual(generated.metadata["fallback_used"], "True")
        finally:
            ai.AI_ENABLED = original_enabled
            ai.OPENAI_API_KEY = original_key

    def test_live_ai_generation_blocks_invalid_citations(self):
        original_enabled = ai.AI_ENABLED
        original_key = ai.OPENAI_API_KEY
        original_call = ai._call_openai
        try:
            ai.AI_ENABLED = True
            ai.OPENAI_API_KEY = "test-key"
            ai._call_openai = lambda payload: {
                "output_text": """{
                    "title": "AI packet",
                    "summary": "AI summary",
                    "suggested_bank_message": "AI message",
                    "claims": [
                        {
                            "id": "claim_bad",
                            "text": "Unsupported AI claim.",
                            "citation_evidence_ids": ["ev_fake"]
                        }
                    ],
                    "next_steps": ["Review citations."]
                }"""
            }
            packet = ai.generate_live_ai_packet(dispute("case_sub_001"), evidence("case_sub_001"))
            self.assertEqual(packet.status, "blocked")
            self.assertEqual(packet.generation_metadata["generator"], "openai_responses")
            self.assertEqual(packet.generation_metadata["model"], "gpt-5.2")
            self.assertEqual(packet.generation_metadata["validation_error_count"], "1")
            self.assertTrue(packet.validation_errors)
            self.assertIn("invalid evidence citation", packet.validation_errors[0])
        finally:
            ai.AI_ENABLED = original_enabled
            ai.OPENAI_API_KEY = original_key
            ai._call_openai = original_call

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

    def test_export_consent_requires_all_acknowledgements(self):
        init_db()
        dispute_id = f"case_{uuid4().hex}"
        save_dispute(replace(dispute("case_sub_001"), id=dispute_id), DEMO_USER_ID)
        for artifact in evidence("case_sub_001"):
            save_evidence(
                replace(artifact, id=f"{artifact.id}_{uuid4().hex[:8]}", dispute_id=dispute_id),
                DEMO_USER_ID,
            )
        api.generate_packet(dispute_id, user_id=DEMO_USER_ID, mode="template")

        with self.assertRaises(ValueError):
            api.export_packet(dispute_id, user_id=DEMO_USER_ID)

        with self.assertRaises(ValueError):
            api.record_export_consent(
                dispute_id,
                {"truthful": True, "reviewed": True, "no_advice": False},
                user_id=DEMO_USER_ID,
            )

        result = api.record_export_consent(
            dispute_id,
            {"truthful": True, "reviewed": True, "no_advice": True},
            user_id=DEMO_USER_ID,
        )
        self.assertTrue(result["ok"])
        logs = list_audit_logs(DEMO_USER_ID)
        self.assertTrue(
            any(
                entry.action == "packet.export_consent_acknowledged" and entry.entity_id == dispute_id
                for entry in logs
            )
        )
        html = api.export_packet(dispute_id, user_id=DEMO_USER_ID)
        self.assertIn("Save as PDF", html)

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
        self.assertFalse(signup["user"]["email_verified"])

        login = api.login({"email": email, "password": "secure-test-password"})
        current = api.current_user(login["token"])
        self.assertEqual(current["email"], email)

    def test_email_verification_marks_user_verified(self):
        init_db()
        email = f"verify-{uuid4().hex[:8]}@example.com"
        signup = api.signup({"name": "Verify User", "email": email, "password": "secure-test-password"})
        token = api._create_auth_token(signup["user"]["id"], "email_verification", 1)
        api.verify_email({"token": token.token})
        login = api.login({"email": email, "password": "secure-test-password"})
        self.assertTrue(login["user"]["email_verified"])

    def test_password_reset_updates_password(self):
        init_db()
        email = f"reset-{uuid4().hex[:8]}@example.com"
        signup = api.signup({"name": "Reset User", "email": email, "password": "old-password"})
        token = api._create_auth_token(signup["user"]["id"], "password_reset", 1)
        api.reset_password({"token": token.token, "password": "new-password"})
        login = api.login({"email": email, "password": "new-password"})
        self.assertEqual(login["user"]["email"], email)
        with self.assertRaises(PermissionError):
            api.login({"email": email, "password": "old-password"})

    def test_test_email_reports_unconfigured_delivery(self):
        init_db()
        login = api.demo_login()
        result = api.send_account_test_email(login["user"]["id"])
        self.assertFalse(result["email_sent"])
        self.assertFalse(result["email_delivery_configured"])

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
        self.assertIn("configured", payload["checks"]["email"])
        self.assertIn("configured", payload["checks"]["ai"])
        self.assertIn("jobs", payload["checks"])
        self.assertIn("stale_queued", payload["checks"]["jobs"])

    def test_job_runner_endpoint_requires_token(self):
        original = os.environ.get("JOB_RUN_TOKEN")
        try:
            os.environ["JOB_RUN_TOKEN"] = "job-secret"

            class Headers(dict):
                def get(self, key, default=None):
                    return super().get(key, default)

            handler = object.__new__(Handler)
            handler.headers = Headers()
            with self.assertRaises(PermissionError):
                handler._validate_job_run_token()

            handler.headers = Headers({"X-Job-Run-Token": "job-secret"})
            handler._validate_job_run_token()
        finally:
            if original is None:
                os.environ.pop("JOB_RUN_TOKEN", None)
            else:
                os.environ["JOB_RUN_TOKEN"] = original

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
        self.assertIn("export_consents", exported)
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
        filename = f"tracking-{uuid4().hex[:8]}.txt"
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
                "filename": filename,
                "content_type": "text/plain",
                "data": b"No delivery scan",
            },
            DEMO_USER_ID,
        )
        files = list_evidence_files(DEMO_USER_ID, "case_delivery_002")
        self.assertTrue(any(file.original_filename == filename for file in files))
        jobs = api.job_status(DEMO_USER_ID)["jobs"]
        self.assertTrue(any(job["job_type"] == "evidence_file.post_upload_processing" for job in jobs))
        completed = api.run_jobs()["completed"]
        self.assertTrue(any(job["status"] == "completed" for job in completed))
        processed = next(file for file in list_evidence_files(DEMO_USER_ID, "case_delivery_002") if file.original_filename == filename)
        self.assertEqual(processed.extraction_status, "extracted")
        self.assertEqual(processed.extracted_text, "No delivery scan")
        exported = api.export_account_data(DEMO_USER_ID)
        self.assertIn("evidence_files", exported)

    def test_background_job_retries_with_backoff_before_failing(self):
        init_db()
        original_process = jobs._process_job
        original_max_attempts = jobs.MAX_JOB_ATTEMPTS
        try:
            jobs.MAX_JOB_ATTEMPTS = 2
            jobs._process_job = lambda job: (_ for _ in ()).throw(RuntimeError("temporary failure"))
            job_id = f"job_{uuid4().hex[:12]}"
            save_background_job(
                BackgroundJob(
                    id=job_id,
                    owner_id=DEMO_USER_ID,
                    job_type="evidence_file.post_upload_processing",
                    status="queued",
                    attempts=0,
                    payload={"file_id": "missing"},
                    last_error="",
                    run_after="2026-05-21T12:00:00Z",
                    created_at="2026-05-21T12:00:00Z",
                    updated_at="2026-05-21T12:00:00Z",
                )
            )

            first = next(job for job in jobs.run_once("2026-05-21T12:00:00Z", limit=1000) if job.id == job_id)
            self.assertEqual(first.status, "queued")
            self.assertEqual(first.attempts, 1)
            self.assertEqual(first.run_after, "2026-05-21T12:01:00Z")
            self.assertEqual(jobs.summarize_run([first]), {"processed": 1, "completed": 0, "retried": 1, "failed": 0})

            early = jobs.run_once("2026-05-21T12:00:30Z", limit=1000)
            self.assertFalse(any(job.id == job_id for job in early))

            second = next(job for job in jobs.run_once("2026-05-21T12:01:00Z", limit=1000) if job.id == job_id)
            self.assertEqual(second.status, "failed")
            self.assertEqual(second.attempts, 2)
            self.assertIn("temporary failure", second.last_error)
            self.assertEqual(jobs.summarize_run([second]), {"processed": 1, "completed": 0, "retried": 0, "failed": 1})
        finally:
            jobs._process_job = original_process
            jobs.MAX_JOB_ATTEMPTS = original_max_attempts

    def test_background_job_health_flags_stale_queued_jobs(self):
        init_db()
        save_background_job(
            BackgroundJob(
                id=f"job_{uuid4().hex[:12]}",
                owner_id=DEMO_USER_ID,
                job_type="evidence_file.post_upload_processing",
                status="queued",
                attempts=1,
                payload={"file_id": "missing"},
                last_error="temporary failure",
                run_after="2026-05-21T11:00:00Z",
                created_at="2026-05-21T10:00:00Z",
                updated_at="2026-05-21T10:00:00Z",
            )
        )
        health = jobs.health("2026-05-21T12:00:00Z")
        self.assertFalse(health["healthy"])
        self.assertGreaterEqual(health["stale_queued"], 1)

    def test_admin_job_status_lists_recent_jobs_without_payload_values(self):
        init_db()
        job_id = f"job_{uuid4().hex[:12]}"
        save_background_job(
            BackgroundJob(
                id=job_id,
                owner_id=DEMO_USER_ID,
                job_type="evidence_file.post_upload_processing",
                status="failed",
                attempts=3,
                payload={"file_id": "file_sensitive", "dispute_id": "case_sensitive"},
                last_error="S3 timeout",
                run_after="2026-05-21T12:00:00Z",
                created_at="2026-05-21T12:00:00Z",
                updated_at="2026-05-21T12:05:00Z",
            )
        )
        payload = api.admin_job_status(limit=100)
        job = next(item for item in payload["jobs"] if item["id"] == job_id)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["last_error"], "S3 timeout")
        self.assertEqual(job["payload_keys"], ["dispute_id", "file_id"])
        self.assertNotIn("file_sensitive", str(job))

    def test_admin_retry_job_requeues_failed_job_without_payload_values(self):
        init_db()
        job_id = f"job_{uuid4().hex[:12]}"
        save_background_job(
            BackgroundJob(
                id=job_id,
                owner_id=DEMO_USER_ID,
                job_type="evidence_file.post_upload_processing",
                status="failed",
                attempts=3,
                payload={"file_id": "file_sensitive"},
                last_error="S3 timeout",
                run_after="2026-05-21T12:00:00Z",
                created_at="2026-05-21T12:00:00Z",
                updated_at="2026-05-21T12:05:00Z",
            )
        )
        payload = api.admin_retry_job(job_id)
        self.assertEqual(payload["job"]["status"], "queued")
        self.assertEqual(payload["job"]["attempts"], 0)
        self.assertEqual(payload["job"]["last_error"], "")
        self.assertEqual(payload["job"]["payload_keys"], ["file_id"])
        self.assertNotIn("file_sensitive", str(payload))

        stored = get_background_job(job_id)
        self.assertEqual(stored.status, "queued")
        self.assertEqual(stored.attempts, 0)
        self.assertEqual(stored.last_error, "")

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

    def test_s3_storage_uses_object_storage_credentials(self):
        import chargeback_copilot.uploads as uploads

        class FakeBoto3:
            kwargs = None

            @classmethod
            def client(cls, service, **kwargs):
                cls.kwargs = kwargs
                return object()

        original_boto3 = uploads.boto3
        original_backend = uploads.OBJECT_STORAGE_BACKEND
        original_bucket = uploads.OBJECT_STORAGE_BUCKET
        original_key = uploads.OBJECT_STORAGE_ACCESS_KEY_ID
        original_secret = uploads.OBJECT_STORAGE_SECRET_ACCESS_KEY
        try:
            uploads.boto3 = FakeBoto3
            uploads.OBJECT_STORAGE_BACKEND = "s3"
            uploads.OBJECT_STORAGE_BUCKET = "test-bucket"
            uploads.OBJECT_STORAGE_ACCESS_KEY_ID = "test-key"
            uploads.OBJECT_STORAGE_SECRET_ACCESS_KEY = "test-secret"
            uploads.storage_adapter()
            self.assertEqual(FakeBoto3.kwargs["aws_access_key_id"], "test-key")
            self.assertEqual(FakeBoto3.kwargs["aws_secret_access_key"], "test-secret")
        finally:
            uploads.boto3 = original_boto3
            uploads.OBJECT_STORAGE_BACKEND = original_backend
            uploads.OBJECT_STORAGE_BUCKET = original_bucket
            uploads.OBJECT_STORAGE_ACCESS_KEY_ID = original_key
            uploads.OBJECT_STORAGE_SECRET_ACCESS_KEY = original_secret

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
