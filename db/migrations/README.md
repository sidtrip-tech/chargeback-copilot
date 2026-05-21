# Database Migrations

This folder contains production database migration artifacts.

## Current State

- The hosted demo still runs on SQLite so it can deploy as a single service.
- `001_initial_postgres_schema.sql` is the target schema for the managed Postgres production move.
- The next implementation slice should add a Postgres store adapter and migration runner before changing `render.yaml` to use managed Postgres.

## Intended Production Flow

1. Create a managed Postgres database in the hosting provider.
2. Apply migrations with `DATABASE_URL="postgresql://..." python3 scripts/migrate_db.py`.
3. Deploy the app with `DATABASE_URL=postgresql://...`.
4. Run `DATABASE_URL="postgresql://..." SEED_DEMO_DATA=true python3 scripts/postgres_smoke.py`.
5. Remove the SQLite persistent disk from production after data migration is complete.

## Why The Schema Keeps `payload`

The current prototype serializes domain objects as JSON. The production schema exposes important fields as typed columns for querying and indexes, while keeping `payload JSONB` as a compatibility layer during the transition. Later migrations should gradually reduce reliance on full-object payloads.
