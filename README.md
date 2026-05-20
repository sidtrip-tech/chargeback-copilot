# Chargeback Copilot

Chargeback Copilot is a local MVP for helping people prepare legitimate payment dispute packets for their bank or card issuer.

The first artifact in this repo is the product requirements document:

- [Chargeback Copilot PRD](docs/chargeback-copilot-prd.md)

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

## Run Locally

```bash
python3 backend/server.py
```

Then open:

```text
http://127.0.0.1:8010
```

The app uses a local SQLite database at `backend/chargeback_copilot.db`, which is created automatically on first run.

## What You Can Do

- Review seeded consumer dispute examples.
- Start a new dispute packet.
- Add manual evidence entries.
- See category-specific evidence checklists.
- Review evidence gaps before export.
- Generate a cited dispute packet.
- Export a bank-ready HTML packet.

## Tests

```bash
python3 -m unittest discover backend/tests
```

## Safety Boundaries

Chargeback Copilot is a preparation tool only. It does not submit disputes directly, provide legal or financial advice, or guarantee outcomes. Generated factual claims must cite evidence, and weak cases are shown as evidence gaps instead of invented support.
