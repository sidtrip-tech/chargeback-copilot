import json
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from .auth import DEMO_EMAIL, DEMO_NAME, DEMO_USER_ID, hash_password, new_session_token
from .models import (
    AuditLog,
    CitedClaim,
    ConsumerDispute,
    EvidenceArtifact,
    EvidenceGap,
    OutcomeFeedback,
    Packet,
    TimelineEvent,
    User,
)
from .seed_data import DISPUTES, EVIDENCE


def _resolve_db_path() -> Path:
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("sqlite:///"):
        raw_path = database_url.removeprefix("sqlite:///")
        return Path(raw_path).expanduser()
    return Path(__file__).resolve().parents[1] / "chargeback_copilot.db"


DB_PATH = _resolve_db_path()


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS disputes (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
                id TEXT PRIMARY KEY,
                dispute_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS packets (
                id TEXT PRIMARY KEY,
                dispute_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outcomes (
                dispute_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata TEXT NOT NULL
            );
            """
        )
        _ensure_owner_columns(conn)
        _ensure_demo_user(conn)
        if conn.execute("SELECT COUNT(*) FROM disputes").fetchone()[0] == 0:
            for dispute in DISPUTES:
                conn.execute(
                    "INSERT INTO disputes (id, owner_id, payload) VALUES (?, ?, ?)",
                    (dispute.id, DEMO_USER_ID, json.dumps(asdict(dispute))),
                )
            for evidence in EVIDENCE:
                conn.execute(
                    "INSERT INTO evidence (id, dispute_id, owner_id, payload) VALUES (?, ?, ?, ?)",
                    (evidence.id, evidence.dispute_id, DEMO_USER_ID, json.dumps(asdict(evidence))),
                )
        _backfill_owner_ids(conn)
        conn.commit()
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_owner_columns(conn: sqlite3.Connection) -> None:
    owner_tables = ("disputes", "evidence", "packets", "outcomes")
    for table in owner_tables:
        if "owner_id" not in _columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN owner_id TEXT")


def _ensure_demo_user(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM users WHERE id = ?", (DEMO_USER_ID,)).fetchone():
        return
    conn.execute(
        "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
        (
            DEMO_USER_ID,
            DEMO_EMAIL,
            DEMO_NAME,
            hash_password("demo-password"),
            "2026-05-20T12:00:00Z",
        ),
    )


def _backfill_owner_ids(conn: sqlite3.Connection) -> None:
    for table in ("disputes", "evidence", "packets", "outcomes"):
        conn.execute(f"UPDATE {table} SET owner_id = ? WHERE owner_id IS NULL OR owner_id = ''", (DEMO_USER_ID,))


def _load_dataclass(cls, payload: str):
    return cls(**json.loads(payload))


def _load_packet(payload: str) -> Packet:
    data = json.loads(payload)
    data["claims"] = [CitedClaim(**claim) for claim in data["claims"]]
    data["timeline"] = [TimelineEvent(**event) for event in data["timeline"]]
    data["evidence_gaps"] = [EvidenceGap(**gap) for gap in data["evidence_gaps"]]
    return Packet(**data)


def _load_outcome(payload: str) -> OutcomeFeedback:
    return OutcomeFeedback(**json.loads(payload))


def get_user(user_id: str) -> User:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise KeyError(user_id)
        return User(
            id=row["id"],
            email=row["email"],
            name=row["name"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
        )
    finally:
        conn.close()


def create_session(user_id: str, created_at: str, expires_at: str) -> str:
    token = new_session_token()
    conn = connect()
    try:
        conn.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", (token, user_id, created_at, expires_at))
        conn.commit()
        return token
    finally:
        conn.close()


def get_session_user(token: str, now: str) -> Optional[User]:
    if not token:
        return None
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT users.*
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ? AND sessions.expires_at > ?
            """,
            (token, now),
        ).fetchone()
        if not row:
            return None
        return User(
            id=row["id"],
            email=row["email"],
            name=row["name"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
        )
    finally:
        conn.close()


def delete_session(token: str) -> None:
    conn = connect()
    try:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


def list_disputes(owner_id: str = DEMO_USER_ID) -> List[ConsumerDispute]:
    conn = connect()
    try:
        return [
            _load_dataclass(ConsumerDispute, row["payload"])
            for row in conn.execute("SELECT payload FROM disputes WHERE owner_id = ? ORDER BY id", (owner_id,)).fetchall()
        ]
    finally:
        conn.close()


def get_dispute(dispute_id: str, owner_id: str = DEMO_USER_ID) -> ConsumerDispute:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT payload FROM disputes WHERE id = ? AND owner_id = ?",
            (dispute_id, owner_id),
        ).fetchone()
        if not row:
            raise KeyError(dispute_id)
        return _load_dataclass(ConsumerDispute, row["payload"])
    finally:
        conn.close()


def save_dispute(dispute: ConsumerDispute, owner_id: str = DEMO_USER_ID) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO disputes (id, owner_id, payload) VALUES (?, ?, ?)",
            (dispute.id, owner_id, json.dumps(asdict(dispute))),
        )
        conn.commit()
    finally:
        conn.close()


def list_evidence(dispute_id: str, owner_id: str = DEMO_USER_ID) -> List[EvidenceArtifact]:
    conn = connect()
    try:
        return [
            _load_dataclass(EvidenceArtifact, row["payload"])
            for row in conn.execute(
                "SELECT payload FROM evidence WHERE dispute_id = ? AND owner_id = ?",
                (dispute_id, owner_id),
            ).fetchall()
        ]
    finally:
        conn.close()


def save_evidence(evidence: EvidenceArtifact, owner_id: str = DEMO_USER_ID) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO evidence (id, dispute_id, owner_id, payload) VALUES (?, ?, ?, ?)",
            (evidence.id, evidence.dispute_id, owner_id, json.dumps(asdict(evidence))),
        )
        conn.commit()
    finally:
        conn.close()


def save_packet(packet: Packet, owner_id: str = DEMO_USER_ID) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO packets (id, dispute_id, owner_id, payload) VALUES (?, ?, ?, ?)",
            (packet.id, packet.dispute_id, owner_id, json.dumps(asdict(packet))),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_packet(dispute_id: str, owner_id: str = DEMO_USER_ID) -> Optional[Packet]:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT payload FROM packets
            WHERE dispute_id = ? AND owner_id = ?
            ORDER BY json_extract(payload, '$.created_at') DESC
            LIMIT 1
            """,
            (dispute_id, owner_id),
        ).fetchone()
        return _load_packet(row["payload"]) if row else None
    finally:
        conn.close()


def save_outcome(outcome: OutcomeFeedback, owner_id: str = DEMO_USER_ID) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO outcomes (dispute_id, owner_id, payload) VALUES (?, ?, ?)",
            (outcome.dispute_id, owner_id, json.dumps(asdict(outcome))),
        )
        conn.commit()
    finally:
        conn.close()


def get_outcome(dispute_id: str, owner_id: str = DEMO_USER_ID) -> Optional[OutcomeFeedback]:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT payload FROM outcomes WHERE dispute_id = ? AND owner_id = ?",
            (dispute_id, owner_id),
        ).fetchone()
        return _load_outcome(row["payload"]) if row else None
    finally:
        conn.close()


def save_audit_log(entry: AuditLog) -> None:
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO audit_logs (id, user_id, action, entity_type, entity_id, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                entry.user_id,
                entry.action,
                entry.entity_type,
                entry.entity_id,
                entry.created_at,
                json.dumps(entry.metadata),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_audit_logs(user_id: str) -> List[AuditLog]:
    conn = connect()
    try:
        return [
            AuditLog(
                id=row["id"],
                user_id=row["user_id"],
                action=row["action"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                created_at=row["created_at"],
                metadata=json.loads(row["metadata"]),
            )
            for row in conn.execute(
                "SELECT * FROM audit_logs WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        ]
    finally:
        conn.close()
