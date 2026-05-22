# Deployment Guide

## First Deploy Target

Use a single Docker web service plus managed Render Postgres. The service runs the Python server, serves the static frontend, and stores app data in Postgres through `DATABASE_URL`.

This is deployment-ready for a controlled production-style demo. The next production upgrade should replace local auth with hosted auth or add email verification and password reset.

## Render Deployment

1. Push the repo to GitHub.
2. In Render, create a new Blueprint from this repo.
3. Render will read `render.yaml`.
4. Confirm it will create:
   - web service `chargeback-copilot`
   - Postgres database `chargeback-copilot-db`
5. Deploy the Blueprint.
6. Open the public URL and check `/api/health`.
7. For a deeper production check, open `/api/readiness` after database and storage env vars are set.

After deployment, use the checklist in [Runbooks](runbooks.md) for the production smoke test.

Expected health response:

```json
{
  "ok": true,
  "service": "chargeback-copilot",
  "timestamp": "..."
}
```

Expected readiness response:

```json
{
  "ok": true,
  "service": "chargeback-copilot",
  "timestamp": "...",
  "checks": {
    "database": { "ok": true, "backend": "postgres" },
    "storage": { "ok": true, "backend": "s3", "bucket": "your-private-bucket" },
    "email": { "ok": true, "configured": true, "host": "smtp.your-provider.com", "from_email": "support@your-domain.com" }
  }
}
```

`/api/readiness` writes, reads, and deletes a tiny storage healthcheck object. Use it manually after changing storage settings; keep `/api/health` as the platform health check.

## Manual Docker Run

```bash
docker build -t chargeback-copilot .
docker run --rm -p 8010:8010 \
  -e HOST=0.0.0.0 \
  -e PORT=8010 \
  -e DATABASE_URL=sqlite:////tmp/chargeback_copilot.db \
  chargeback-copilot
```

Then open:

```text
http://127.0.0.1:8010
```

## Production Gaps After First Deploy

- Replace local auth with hosted auth, or add email verification and password reset.
- Add hosted-auth-grade CSRF/CORS middleware or WAF/CDN protections.
- Add secure evidence uploads and object storage.
- Add external monitoring and error tracking beyond the current request IDs and structured Render logs.
- Add staging and production environment separation.
- Replace the local account deletion/export flow with a reviewed privacy operations process before handling real sensitive evidence at scale.

## Render Postgres

`render.yaml` provisions a managed Postgres database:

```yaml
databases:
  - name: chargeback-copilot-db
    plan: basic-256mb
```

The web service receives the internal connection string through:

```yaml
fromDatabase:
  name: chargeback-copilot-db
  property: connectionString
```

The app applies migrations on startup. You can also run the migration script manually from a Render shell or locally with a database URL:

```bash
DATABASE_URL="postgresql://..." python3 scripts/migrate_db.py
```

For staging validation:

```bash
DATABASE_URL="postgresql://..." SEED_DEMO_DATA=true python3 scripts/postgres_smoke.py
```

## Current Security Hardening

The stdlib server includes a few production-foundation protections:

- HttpOnly session cookies, with `Secure` enabled when `APP_ENV=production`.
- Double-submit CSRF protection for cookie-authenticated POST requests.
- Origin allowlist checks for state-changing requests through `CORS_ALLOWED_ORIGINS`.
- Basic auth endpoint rate limiting through `AUTH_RATE_LIMIT_ATTEMPTS` and `AUTH_RATE_LIMIT_WINDOW_SECONDS`.
- Email verification and password reset token endpoints, with optional SMTP delivery.
- JSON request body size limit through `MAX_JSON_BODY_BYTES`.
- Browser security headers: `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, and `Permissions-Policy`.
- User data export and account deletion endpoints.
- Evidence upload type and size limits with generated storage keys, owner-checked downloads, and delete controls.

Evidence upload note: the current Render config keeps `OBJECT_STORAGE_BACKEND=local`, which stores uploaded file bytes under `/tmp`. That is acceptable only for workflow validation because files are ephemeral. Real production should switch to S3-compatible object storage before real users upload sensitive files.

S3-compatible storage configuration:

```text
OBJECT_STORAGE_BACKEND=s3
OBJECT_STORAGE_BUCKET=your-private-bucket
OBJECT_STORAGE_REGION=us-east-1
OBJECT_STORAGE_ENDPOINT=
OBJECT_STORAGE_ACCESS_KEY_ID=...
OBJECT_STORAGE_SECRET_ACCESS_KEY=...
```

For S3-compatible providers outside AWS, set `OBJECT_STORAGE_ENDPOINT` to the provider endpoint. Uploaded objects are written with generated keys and server-side encryption enabled. File downloads are proxied through authenticated app routes so the storage bucket can stay private.

After setting these variables, redeploy and check:

```text
https://your-render-service.onrender.com/api/readiness
```

## Email Verification And Password Reset

The app can create verification and password reset tokens without SMTP, but production email delivery requires SMTP settings:

```text
PUBLIC_BASE_URL=https://chargeback-copilot.onrender.com
SMTP_HOST=smtp.your-provider.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM_EMAIL=support@your-domain.com
SMTP_USE_TLS=true
```

Use a transactional email provider or a verified SMTP sender. Without these values, the UI will show that email delivery is not configured.

After SMTP is configured, sign in and use **Send test email** in the sidebar. That sends a harmless test message to the current account email and is the quickest way to confirm Render can reach the SMTP provider.

## Optional AI Drafting

AI drafting is optional. Template generation remains the fallback and works without an API key.

```text
AI_ENABLED=true
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.2
```

The `live_ai` generation mode sends only the dispute fields, evidence summaries, checklist strategy, and evidence gaps to the model. It requires structured JSON output and then runs the same citation validation used by template generation. If AI is unavailable or fails, the app generates a template draft and marks the packet as a fallback.

After enabling AI:

1. Open `/api/readiness` and confirm `ai.configured` is `true`.
2. In GitHub repository variables, set `MONITOR_EXPECT_AI_CONFIGURED=true` if production should alert when AI is disabled.
3. In the app, open an in-progress packet, select **Live AI**, and generate a packet.
4. Confirm the generated claims all show evidence IDs and export remains blocked if high-priority evidence gaps remain.

## PDF-Ready Export

Packet export is currently PDF-ready HTML. The export page includes print styles and a **Save as PDF** button that opens the browser print dialog. This avoids adding a server-side PDF renderer before the core packet and evidence workflow stabilizes.

Native PDF generation is still a future upgrade. When added, it should run as a background job and store generated PDFs in object storage.

## Background Jobs

The app includes a minimal background job table and worker command:

```bash
python3 scripts/run_jobs.py
```

Evidence uploads enqueue a `evidence_file.post_upload_processing` job. The current worker marks placeholder jobs complete. Future work should route by job type for malware scanning, OCR, native PDF rendering, and AI preparation.

On Render, this can become a separate Worker service that runs the same Docker image with:

```bash
python3 scripts/run_jobs.py
```

For production, change it from one-shot execution to a polling worker or scheduled job.

## Upload Scanning

The app records a `scan_status` for each uploaded evidence file:

- `not_configured` when scanning is disabled.
- `clean` when the configured scanner passes the file.
- blocked upload with HTTP `422` when the scanner rejects the file.

Current config supports a basic EICAR-style test scanner:

```text
VIRUS_SCAN_ENABLED=true
VIRUS_SCAN_MODE=basic
```

That is useful for validating the scan/blocking path. Before real sensitive uploads at scale, replace or extend this with managed malware scanning, such as an object-storage scan pipeline or a dedicated scanning service.

These are useful guardrails for the current app, but they are not a replacement for hosted auth, WAF/CDN protections, or framework-level middleware in a full production backend.

After Render gives you the production URL, set:

```text
CORS_ALLOWED_ORIGINS=https://your-render-service.onrender.com
```

If you later put the app behind a custom domain, add that domain too:

```text
CORS_ALLOWED_ORIGINS=https://your-render-service.onrender.com,https://chargebackcopilot.com
```
