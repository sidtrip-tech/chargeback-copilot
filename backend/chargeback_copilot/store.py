import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from .models import (
    CitedClaim,
    ConsumerDispute,
    EvidenceArtifact,
    EvidenceGap,
    Packet,
    TimelineEvent,
)
from .seed_data import DISPUTES, EVIDENCE


DB_PATH = Path(__file__).resolve().parents[1] / "chargeback_copilot.db"


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS disputes (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
                id TEXT PRIMARY KEY,
                dispute_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS packets (
                id TEXT PRIMARY KEY,
                dispute_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            """
        )
        if conn.execute("SELECT COUNT(*) FROM disputes").fetchone()[0] == 0:
            for dispute in DISPUTES:
                conn.execute("INSERT INTO disputes VALUES (?, ?)", (dispute.id, json.dumps(asdict(dispute))))
            for evidence in EVIDENCE:
                conn.execute(
                    "INSERT INTO evidence VALUES (?, ?, ?)",
                    (evidence.id, evidence.dispute_id, json.dumps(asdict(evidence))),
                )
        conn.commit()
    finally:
        conn.close()


def _load_dataclass(cls, payload: str):
    return cls(**json.loads(payload))


def _load_packet(payload: str) -> Packet:
    data = json.loads(payload)
    data["claims"] = [CitedClaim(**claim) for claim in data["claims"]]
    data["timeline"] = [TimelineEvent(**event) for event in data["timeline"]]
    data["evidence_gaps"] = [EvidenceGap(**gap) for gap in data["evidence_gaps"]]
    return Packet(**data)


def list_disputes() -> List[ConsumerDispute]:
    conn = connect()
    try:
        return [
            _load_dataclass(ConsumerDispute, row["payload"])
            for row in conn.execute("SELECT payload FROM disputes ORDER BY id").fetchall()
        ]
    finally:
        conn.close()


def get_dispute(dispute_id: str) -> ConsumerDispute:
    conn = connect()
    try:
        row = conn.execute("SELECT payload FROM disputes WHERE id = ?", (dispute_id,)).fetchone()
        if not row:
            raise KeyError(dispute_id)
        return _load_dataclass(ConsumerDispute, row["payload"])
    finally:
        conn.close()


def save_dispute(dispute: ConsumerDispute) -> None:
    conn = connect()
    try:
        conn.execute("INSERT OR REPLACE INTO disputes VALUES (?, ?)", (dispute.id, json.dumps(asdict(dispute))))
        conn.commit()
    finally:
        conn.close()


def list_evidence(dispute_id: str) -> List[EvidenceArtifact]:
    conn = connect()
    try:
        return [
            _load_dataclass(EvidenceArtifact, row["payload"])
            for row in conn.execute("SELECT payload FROM evidence WHERE dispute_id = ?", (dispute_id,)).fetchall()
        ]
    finally:
        conn.close()


def save_evidence(evidence: EvidenceArtifact) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO evidence VALUES (?, ?, ?)",
            (evidence.id, evidence.dispute_id, json.dumps(asdict(evidence))),
        )
        conn.commit()
    finally:
        conn.close()


def save_packet(packet: Packet) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO packets VALUES (?, ?, ?)",
            (packet.id, packet.dispute_id, json.dumps(asdict(packet))),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_packet(dispute_id: str) -> Optional[Packet]:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT payload FROM packets WHERE dispute_id = ? ORDER BY json_extract(payload, '$.created_at') DESC LIMIT 1",
            (dispute_id,),
        ).fetchone()
        return _load_packet(row["payload"]) if row else None
    finally:
        conn.close()

