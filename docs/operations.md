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
