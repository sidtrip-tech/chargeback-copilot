# Operations Guide

## Health Checks

Use `/api/health` for platform health checks. It confirms the app process is running.

Use `/api/readiness` manually after deployment or environment changes. It checks:

- database connectivity
- evidence storage read/write/delete
- email configuration status

## Request IDs

Every response includes an `X-Request-ID` header. Error responses also include `request_id` in the JSON body, and the frontend shows it in user-facing error messages.

When debugging a user report:

1. Ask for the request ID shown in the error message.
2. Open Render service logs.
3. Search for that request ID.
4. Review the matching `request.started`, `request.error`, and `request.completed` JSON log lines.

## Structured Logs

The backend writes JSON logs to stdout. Render captures these logs automatically.

Common events:

- `server.started`
- `request.started`
- `request.completed`
- `request.error`

Example error log fields:

```json
{
  "event": "request.error",
  "request_id": "req_...",
  "method": "POST",
  "path": "/api/disputes",
  "status": 400,
  "error_type": "ValueError",
  "error": "Merchant name is required."
}
```

Do not log passwords, full evidence text, raw uploaded file contents, session cookies, CSRF tokens, or card numbers.

## Deployment Smoke Test

After each deploy:

1. Open `/api/health`.
2. Open `/api/readiness`.
3. Sign in.
4. Create or open a packet.
5. Upload and download a small evidence file.
6. Generate and export a packet.
7. Send a test email if SMTP is configured.

## Backup And Recovery

Production data has two durable stores:

- Render Postgres for accounts, packet metadata, evidence metadata, generated packets, outcomes, sessions, and audit logs.
- S3-compatible object storage for uploaded evidence files.

### Render Postgres

Before real users:

1. Confirm the Render Postgres plan includes automated backups.
2. Document the backup retention window from the Render database page.
3. Run a restore drill into a separate staging database before launch.
4. Keep `DATABASE_URL` secret and rotate credentials after any accidental exposure.

Restore drill:

1. Create or restore to a separate Postgres database.
2. Point a staging Render service at the restored database.
3. Run `/api/readiness`.
4. Sign in with a test account and confirm packets/evidence metadata load.
5. Do not point production at a restored database until the restored data has been validated.

### S3 Evidence Bucket

Before real users:

1. Keep the bucket private.
2. Enable bucket versioning.
3. Confirm default server-side encryption is on.
4. Restrict the app IAM user to the one evidence bucket.
5. Consider lifecycle rules for old object versions after the retention policy is defined.

Recovery drill:

1. Upload a test evidence file through the app.
2. Confirm the object exists in S3.
3. Download it from the app.
4. Delete the app metadata for the file in a staging copy or use a non-production test object.
5. Confirm object versioning can recover a prior object version if needed.

### Recovery Targets

For the current controlled beta, use provisional targets:

- RPO: 24 hours, aligned to managed database backup cadence.
- RTO: 4 hours for a manual restore and validation.

Tighten these targets before a public launch.

## Incident Notes

For any production incident, capture:

- start time and end time
- affected users or flows
- request IDs from user-facing errors
- Render deploy ID or commit SHA
- relevant database/storage/email provider status
- remediation taken
- follow-up prevention item
