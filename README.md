# Chargeback Copilot

Chargeback Copilot is a local MVP for helping people prepare legitimate payment dispute packets for their bank or card issuer.

The first artifact in this repo is the product requirements document:

- [Chargeback Copilot PRD](docs/chargeback-copilot-prd.md)
- [Production Roadmap](docs/production-roadmap.md)
- [Deployment Guide](docs/deployment.md)
- [Operations Guide](docs/operations.md)
- [Runbooks](docs/runbooks.md)

## Product Direction

Chargeback Copilot is designed as a careful helper. It should help consumers organize evidence, understand likely dispute categories, identify weak spots, and generate a bank-ready packet without promising outcomes or encouraging unsupported claims.

## MVP Focus

The initial MVP is **Prepare Packet**:

- Guided dispute intake
- Reason/category selection
- Evidence checklist
- Evidence upload or manual evidence entry
- Timeline builder
- Claim strength and gap review
- Cited dispute packet export
- Next-step checklist

Direct bank submission, legal advice, and outcome guarantees are out of scope for v1.

## Production Direction

The current app is a local prototype. A production-grade version needs real accounts, user-owned data boundaries, Postgres, secure file evidence handling, object storage, background jobs, PDF export, compliance language, audit logs, monitoring, backups, and CI/CD.

See the [Production Roadmap](docs/production-roadmap.md) for the phased build plan and readiness checklist.

## Run Locally

```bash
python3 backend/server.py
```

Then open:

```text
http://127.0.0.1:8010
```

The app uses a local SQLite database at `backend/chargeback_copilot.db`, which is created automatically on first run.

You can change the local port when 8010 is already in use:

```bash
PORT=8011 python3 backend/server.py
```

## What You Can Do

- Review seeded consumer dispute examples.
- Start a new dispute packet.
- Add manual evidence entries.
- See category-specific evidence checklists.
- Review evidence gaps before export.
- Generate a cited dispute packet.
- Export a bank-ready HTML packet.

## Production Foundation Started

The app now includes the first production-foundation slice:

- Local demo session endpoint with an HttpOnly session cookie.
- Email/password account creation and sign-in for the local production foundation.
- Protected packet APIs that require a session.
- User-owned packet, evidence, generated packet, and outcome rows.
- Audit-log storage for key workflow events.
- Configurable local server host and port through `HOST` and `PORT`.
- Initial production Postgres schema in `db/migrations/001_initial_postgres_schema.sql`.
- Postgres store adapter path selected by `DATABASE_URL=postgresql://...`.
- Readiness check for database and evidence storage at `/api/readiness`.
- Synthetic production monitor script at `scripts/production_monitor.py`.
- Scheduled GitHub Actions production monitor.
- First-pass CSRF protection, origin checks, auth rate limiting, request body limits, and browser security headers.
- User data export and account deletion controls.
- Evidence file upload with type/size checks, file metadata, download, and delete controls.
- Local/S3-compatible evidence storage adapter selected by `OBJECT_STORAGE_BACKEND`.
- Upload scan-status support with a basic scanner mode.
- PDF-ready HTML packet export with print styling and uploaded-file index.
- Background job foundation with upload processing jobs and one-shot worker script.

This is not yet full production identity. Hosted auth, email verification, password reset, secure uploads, and deployment hardening are tracked in the production roadmap.

## First Hosted Deploy

The repo includes deployment scaffolding for a controlled hosted demo:

- `Dockerfile` for containerized deploys.
- `render.yaml` for Render Blueprint deploys with a managed Postgres database.
- `/api/health` for platform health checks.
- GitHub Actions CI in `.github/workflows/ci.yml`.

See the [Deployment Guide](docs/deployment.md) for the exact steps.

## Tests

```bash
python3 -m unittest discover backend/tests
```

## Database Commands

Apply local or Postgres migrations:

```bash
DATABASE_URL=sqlite:///backend/chargeback_copilot.db python3 scripts/migrate_db.py
```

Run the staging Postgres smoke check:

```bash
DATABASE_URL="postgresql://..." SEED_DEMO_DATA=true python3 scripts/postgres_smoke.py
```

## Safety Boundaries

Chargeback Copilot is a preparation tool only. It does not submit disputes directly, provide legal or financial advice, or guarantee outcomes. Generated factual claims must cite evidence, and weak cases are shown as evidence gaps instead of invented support.
