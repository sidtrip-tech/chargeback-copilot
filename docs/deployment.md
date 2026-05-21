# Deployment Guide

## First Deploy Target

Use a single Docker web service for the first hosted demo. The service runs the Python server, serves the static frontend, and stores local demo data in a persistent SQLite file.

This is deployment-ready for a controlled demo, not the final production architecture. The next production upgrade should move data to managed Postgres and replace demo auth with hosted auth.

## Render Deployment

1. Push the repo to GitHub.
2. In Render, create a new Blueprint from this repo.
3. Render will read `render.yaml`.
4. Confirm the persistent disk is mounted at `/var/data`.
5. Deploy the service.
6. Open the public URL and check `/api/health`.

Expected health response:

```json
{
  "ok": true,
  "service": "chargeback-copilot",
  "timestamp": "..."
}
```

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

- Replace demo auth with hosted auth or full signup/login.
- Move SQLite to managed Postgres with migrations.
- Add CSRF/CORS hardening and rate limits.
- Add secure evidence uploads and object storage.
- Add monitoring and error tracking.
- Add staging and production environment separation.
