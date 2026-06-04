CREATE TABLE IF NOT EXISTS export_consents (
    packet_id TEXT PRIMARY KEY REFERENCES packets(id) ON DELETE CASCADE,
    dispute_id TEXT NOT NULL REFERENCES disputes(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    truthful BOOLEAN NOT NULL,
    reviewed BOOLEAN NOT NULL,
    no_advice BOOLEAN NOT NULL,
    acknowledged_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_export_consents_owner_acknowledged
    ON export_consents(owner_id, acknowledged_at DESC);

CREATE INDEX IF NOT EXISTS idx_export_consents_dispute
    ON export_consents(dispute_id);
