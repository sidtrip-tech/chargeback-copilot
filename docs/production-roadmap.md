# Chargeback Copilot Production Roadmap

## 1. Goal

Move Chargeback Copilot from a local workflow prototype to a secure, durable, multi-user web application while preserving the core product promise:

- Help consumers prepare legitimate dispute packets.
- Require factual claims to map to user-provided evidence.
- Export a packet the user can submit through their official bank or card issuer channel.
- Avoid legal advice, financial advice, direct bank submission, and outcome guarantees.

The current local app proves the workflow. Production work should focus on accounts, data boundaries, secure evidence handling, durable infrastructure, compliance, and operational reliability.

## 2. Target Production Architecture

### Frontend

- Hosted web application for public pages and authenticated workspace.
- Public education/conversion page.
- Authenticated dashboard with In Progress, Completed, and Start New Packet views.
- Secure upload UI for files and manual evidence entry.
- Packet review, export, and outcome tracking flows.

### Backend API

- FastAPI or equivalent production web framework.
- Versioned REST API for authentication, packets, evidence, generation, export, and feedback.
- Request validation and typed response contracts.
- Per-user authorization on every packet, evidence, export, and outcome endpoint.

### Database

- Managed Postgres.
- Schema migrations for all tables and indexes.
- Core tables for users, packets, evidence artifacts, timeline events, generated claims, evidence gaps, exports, outcome feedback, audit logs, and background jobs.

### Evidence Storage

- Managed object storage for uploaded PDFs, images, screenshots, and message files.
- Database stores metadata and storage references, not raw binary content.
- Encrypted storage, signed access URLs, file deletion support, and lifecycle policies.

### Background Jobs

- Async jobs for uploads, virus scanning, OCR/text extraction, packet export, PDF rendering, and future AI processing.
- Retry handling, dead-letter tracking, and job status surfaced in the app when useful.

### AI Services

- AI remains optional.
- Deterministic template generation remains the fallback.
- Live AI generation must use only provided packet details and evidence summaries.
- Citation validation must run after template and AI generation.
- Export remains blocked for unsupported factual claims or high-priority unresolved gaps.

## 3. Production Requirements

### Authentication And User Boundaries

- Real sign up, login, logout, password reset, and session management, or a hosted auth provider.
- User-owned packets and evidence.
- Server-side authorization checks for every object access.
- Secure cookies, CSRF protections where applicable, CORS allowlist, rate limits, and brute-force protections.
- No shared prototype workspace in production.

### Evidence Handling

- Upload PDFs, images, screenshots, emails, and text files.
- Enforce file type, file size, and per-user storage limits.
- Scan uploads before making them available for packet generation.
- Extract text from PDFs/images where useful.
- Show evidence previews when safe and supported.
- Allow users to delete evidence and understand how deletion affects packet readiness.
- Never require or store full card numbers.

### Packet Generation And Export

- Keep deterministic templates for dependable generation.
- Add optional citation-validated AI drafting.
- Store generated packet versions so users can audit changes over time.
- Generate PDF in addition to HTML/Markdown-ready text.
- Include evidence index, citation IDs, next-step checklist, and safety disclaimer in every export.
- Block final export when validation finds unsupported claims or unresolved high-priority requirements.

### Compliance, Privacy, And Safety

- Privacy policy, terms of use, and consent language.
- Clear boundaries: preparation tool only; not legal, financial, banking, or issuer advice.
- No guarantee of refund, success, or issuer outcome.
- User data export and deletion request support.
- Audit logs for packet creation, evidence upload/delete, generation, export, and outcome updates.
- Explicit user confirmation before export that the packet is truthful to the best of their knowledge.
- No model training on user evidence without explicit opt-in consent.

### Operations

- Staging and production environments.
- Secrets manager for API keys, auth secrets, database credentials, and storage credentials.
- CI/CD pipeline with tests, lint/static checks, migrations, and deploy steps.
- Monitoring, error tracking, uptime checks, and alerting.
- Database backups and restore drills.
- Structured logging without sensitive evidence contents.

## 4. Phased Build

### Phase 1: Production Foundation

Objective: Convert the local prototype into a real multi-user app foundation.

Scope:

- Production backend framework and API structure.
- Managed Postgres schema and migrations.
- Real auth or hosted auth integration.
- User-owned packets with authorization checks.
- Packet CRUD, readiness scoring, gap detection, template generation, and outcome feedback on production storage.
- Keep manual evidence entry and current template export.

Exit criteria:

- Users can create accounts and only access their own packets.
- Existing core workflow works against Postgres.
- Tests cover packet status, readiness, citation validation, auth, and cross-user access denial.

Current implementation status:

- Started in the local app with a demo user table, session table, HttpOnly session cookie, protected packet APIs, user-owned packet/evidence/packet/outcome rows, and audit-log storage.
- The local server now supports `HOST` and `PORT` environment variables for deployment-shaped runtime configuration.
- Added first-deploy scaffolding: Dockerfile, Render Blueprint config, `/api/health`, persistent demo SQLite path support, deployment guide, and GitHub Actions CI.
- Remaining Phase 1 work: hosted authentication or real signup/login, Postgres adapter, migration tooling, production session hardening, CSRF/CORS policy, rate limits, and production environment setup.

### Phase 2: Evidence And Export

Objective: Make evidence handling and export production-worthy.

Scope:

- Secure file uploads to object storage.
- File type and size validation.
- Virus scanning pipeline.
- Evidence preview and delete controls.
- OCR/text extraction for common file types.
- PDF export.
- Stronger export validation and packet versioning.

Exit criteria:

- Users can safely upload, preview, use, and delete evidence files.
- Packet exports include cited claims and evidence index.
- Final export is blocked when required evidence or citation validation fails.

### Phase 3: AI-Assisted Preparation

Objective: Add optional AI drafting without weakening evidence discipline.

Scope:

- Optional AI generation mode behind configured API key and product controls.
- AI prompts constrained to user-provided evidence.
- Safety refusals for fabrication, unsupported accusations, hidden facts, or outcome promises.
- OCR/summarization for evidence artifacts.
- Citation validator and unsupported-claim blocker.

Exit criteria:

- AI output cannot pass export validation without citations.
- Unsupported factual claims are flagged.
- Template fallback remains available and reliable.

### Phase 4: Compliance And Launch Readiness

Objective: Prepare for a controlled beta and public MVP.

Scope:

- Privacy policy, terms, consent, and truthfulness confirmation.
- Audit logs and admin support workflows.
- User data deletion/export flows.
- Analytics that avoid sensitive content capture.
- Monitoring, backups, staging, production deploy, and incident response basics.
- Private beta feedback loop.

Exit criteria:

- Production smoke tests pass after deploy.
- Security and privacy review items are documented and resolved or explicitly accepted.
- Beta users can complete the full workflow without staff intervention.

## 5. Test Strategy

### Unit Tests

- Packet status derivation.
- Readiness score and evidence checklist progress.
- Evidence gap detection.
- Citation validation.
- Outcome feedback save/read behavior.
- Export blocking rules.

### Integration Tests

- Auth signup/login/logout/password reset.
- Packet CRUD with user ownership.
- Evidence upload, metadata creation, scan status, preview, and delete.
- Packet generation, validation, export, and outcome feedback.
- Database migrations.

### Security Tests

- Cross-user packet and evidence access attempts.
- Upload abuse: unsupported types, oversized files, malicious file names, and scan failures.
- Rate limits and brute-force protections.
- Unsafe AI prompts asking for fabricated, uncited, or misleading claims.
- Sensitive data logging checks.

### End-To-End Tests

- Public page to authenticated workspace.
- Start packet, add evidence, generate, validate, export.
- In Progress next-best-action workflow.
- Completed export-and-track workflow.
- Outcome feedback update.
- Data deletion/export request flow when implemented.

### Production Smoke Tests

- App loads in production.
- Auth works.
- User can create a packet.
- Evidence upload path works.
- Packet export works.
- Monitoring receives health checks and errors.

## 6. Suggested Environment Variables

```text
APP_ENV=development
DATABASE_URL=postgresql://...
AUTH_SECRET=change-me
SESSION_COOKIE_NAME=chargeback_copilot_session
CORS_ALLOWED_ORIGINS=http://localhost:3000
OBJECT_STORAGE_BUCKET=chargeback-copilot-evidence
OBJECT_STORAGE_REGION=us-east-1
OBJECT_STORAGE_ENDPOINT=
OBJECT_STORAGE_ACCESS_KEY_ID=
OBJECT_STORAGE_SECRET_ACCESS_KEY=
VIRUS_SCAN_ENABLED=false
PDF_EXPORT_ENABLED=true
OPENAI_API_KEY=
OPENAI_MODEL=
SENTRY_DSN=
```

## 7. Production Readiness Checklist

- Real authentication is implemented.
- Users cannot access each other's packets, evidence, exports, or outcomes.
- Postgres migrations are repeatable in staging and production.
- Evidence files are encrypted, scanned, size-limited, type-limited, and deletable.
- Full card numbers are never collected.
- Export validates citations and high-priority evidence requirements.
- AI is optional and cannot bypass citation validation.
- Privacy policy, terms, and consent language are present.
- User data export/deletion flow exists or is operationally supported.
- Audit logs capture sensitive workflow events without storing raw evidence text in logs.
- CI runs unit, integration, and end-to-end tests.
- Staging mirrors production architecture.
- Backups, monitoring, error tracking, and alerting are configured.
