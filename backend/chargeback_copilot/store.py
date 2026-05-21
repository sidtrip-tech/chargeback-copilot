import json
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, List, Optional

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:
    psycopg = None
    dict_row = None
    Jsonb = None

from .auth import DEMO_EMAIL, DEMO_NAME, DEMO_USER_ID, hash_password, new_session_token
from .models import (
    AuthToken,
    AuditLog,
    BackgroundJob,
    CitedClaim,
    ConsumerDispute,
    EvidenceArtifact,
    EvidenceFile,
    EvidenceGap,
    OutcomeFeedback,
    Packet,
    TimelineEvent,
    User,
)
from .seed_data import DISPUTES, EVIDENCE


DATABASE_URL = os.environ.get("DATABASE_URL", "")
ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = ROOT / "db" / "migrations"


def using_postgres() -> bool:
    return DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")


def _resolve_db_path() -> Path:
    if DATABASE_URL.startswith("sqlite:///"):
        raw_path = DATABASE_URL.removeprefix("sqlite:///")
        return Path(raw_path).expanduser()
    return Path(__file__).resolve().parents[1] / "chargeback_copilot.db"


DB_PATH = _resolve_db_path()


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def connect_postgres():
    if psycopg is None:
        raise RuntimeError("Postgres DATABASE_URL requires psycopg. Install requirements.txt before running.")
    database_url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    return psycopg.connect(database_url, row_factory=dict_row)


def init_db(db_path: Path = DB_PATH) -> None:
    if using_postgres():
        init_postgres_db()
        return
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
            CREATE TABLE IF NOT EXISTS evidence_files (
                id TEXT PRIMARY KEY,
                evidence_id TEXT NOT NULL,
                dispute_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS background_jobs (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                payload TEXT NOT NULL,
                last_error TEXT NOT NULL,
                run_after TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                purpose TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT
            );
            """
        )
        _ensure_sqlite_schema(conn)
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


def database_health() -> dict[str, object]:
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute("SELECT 1").fetchone()
            return {"ok": True, "backend": "postgres"}
        finally:
            conn.close()
    conn = connect()
    try:
        conn.execute("SELECT 1").fetchone()
        return {"ok": True, "backend": "sqlite"}
    finally:
        conn.close()


def init_postgres_db() -> None:
    conn = connect_postgres()
    try:
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            conn.execute(migration.read_text())
        _ensure_demo_user_postgres(conn)
        should_seed = os.environ.get("SEED_DEMO_DATA", "true").lower() in {"1", "true", "yes"}
        if should_seed and conn.execute("SELECT COUNT(*) AS count FROM disputes").fetchone()["count"] == 0:
            for dispute in DISPUTES:
                _save_dispute_postgres(conn, dispute, DEMO_USER_ID)
            for evidence in EVIDENCE:
                _save_evidence_postgres(conn, evidence, DEMO_USER_ID)
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


def _ensure_sqlite_schema(conn: sqlite3.Connection) -> None:
    _ensure_owner_columns(conn)
    if "email_verified_at" not in _columns(conn, "users"):
        conn.execute("ALTER TABLE users ADD COLUMN email_verified_at TEXT")


def _ensure_demo_user(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM users WHERE id = ?", (DEMO_USER_ID,)).fetchone():
        return
    conn.execute(
        """
        INSERT INTO users (id, email, name, password_hash, created_at, email_verified_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            DEMO_USER_ID,
            DEMO_EMAIL,
            DEMO_NAME,
            hash_password("demo-password"),
            "2026-05-20T12:00:00Z",
            "2026-05-20T12:00:00Z",
        ),
    )


def _backfill_owner_ids(conn: sqlite3.Connection) -> None:
    for table in ("disputes", "evidence", "packets", "outcomes"):
        conn.execute(f"UPDATE {table} SET owner_id = ? WHERE owner_id IS NULL OR owner_id = ''", (DEMO_USER_ID,))


def _load_payload(payload: Any):
    return payload if isinstance(payload, dict) else json.loads(payload)


def _load_dataclass(cls, payload: Any):
    return cls(**_load_payload(payload))


def _load_packet(payload: Any) -> Packet:
    data = _load_payload(payload)
    data["claims"] = [CitedClaim(**claim) for claim in data["claims"]]
    data["timeline"] = [TimelineEvent(**event) for event in data["timeline"]]
    data["evidence_gaps"] = [EvidenceGap(**gap) for gap in data["evidence_gaps"]]
    return Packet(**data)


def _load_outcome(payload: Any) -> OutcomeFeedback:
    return OutcomeFeedback(**_load_payload(payload))


def _load_evidence_file(payload: Any) -> EvidenceFile:
    return EvidenceFile(**_load_payload(payload))


def _load_auth_token(payload: Any) -> AuthToken:
    return AuthToken(**_load_payload(payload))


def _load_background_job(payload: Any) -> BackgroundJob:
    return BackgroundJob(**_load_payload(payload))


def _json_payload(data: Any):
    return Jsonb(data) if using_postgres() and Jsonb is not None else json.dumps(data)


def _ensure_demo_user_postgres(conn) -> None:
    if conn.execute("SELECT 1 FROM users WHERE id = %s", (DEMO_USER_ID,)).fetchone():
        return
    conn.execute(
        """
        INSERT INTO users (id, email, name, password_hash, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            DEMO_USER_ID,
            DEMO_EMAIL,
            DEMO_NAME,
            hash_password("demo-password"),
            "2026-05-20T12:00:00Z",
            "2026-05-20T12:00:00Z",
        ),
    )


def _user_from_row(row) -> User:
    created_at = row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"]
    verified_at = None
    if "email_verified_at" in row.keys():
        value = row["email_verified_at"]
        verified_at = value.isoformat() if hasattr(value, "isoformat") else value
    return User(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        password_hash=row["password_hash"] or "",
        created_at=created_at,
        email_verified_at=verified_at,
    )


def _save_dispute_postgres(conn, dispute: ConsumerDispute, owner_id: str) -> None:
    payload = asdict(dispute)
    conn.execute(
        """
        INSERT INTO disputes (
            id, owner_id, merchant_name, amount_cents, currency, charge_date, issuer_name,
            category, status, user_summary, payload, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (id) DO UPDATE SET
            owner_id = EXCLUDED.owner_id,
            merchant_name = EXCLUDED.merchant_name,
            amount_cents = EXCLUDED.amount_cents,
            currency = EXCLUDED.currency,
            charge_date = EXCLUDED.charge_date,
            issuer_name = EXCLUDED.issuer_name,
            category = EXCLUDED.category,
            status = EXCLUDED.status,
            user_summary = EXCLUDED.user_summary,
            payload = EXCLUDED.payload,
            updated_at = now()
        """,
        (
            dispute.id,
            owner_id,
            dispute.merchant_name,
            dispute.amount,
            dispute.currency,
            dispute.charge_date,
            dispute.issuer_name,
            dispute.category,
            dispute.status,
            dispute.user_summary,
            _json_payload(payload),
            dispute.created_at,
        ),
    )


def _save_evidence_postgres(conn, evidence: EvidenceArtifact, owner_id: str) -> None:
    payload = asdict(evidence)
    conn.execute(
        """
        INSERT INTO evidence (
            id, dispute_id, owner_id, type, title, source, occurred_at, summary, relevance, payload, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (id) DO UPDATE SET
            dispute_id = EXCLUDED.dispute_id,
            owner_id = EXCLUDED.owner_id,
            type = EXCLUDED.type,
            title = EXCLUDED.title,
            source = EXCLUDED.source,
            occurred_at = EXCLUDED.occurred_at,
            summary = EXCLUDED.summary,
            relevance = EXCLUDED.relevance,
            payload = EXCLUDED.payload,
            updated_at = now()
        """,
        (
            evidence.id,
            evidence.dispute_id,
            owner_id,
            evidence.type,
            evidence.title,
            evidence.source,
            evidence.occurred_at,
            evidence.summary,
            evidence.relevance,
            _json_payload(payload),
        ),
    )


def get_user(user_id: str) -> User:
    if using_postgres():
        conn = connect_postgres()
        try:
            row = conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
            if not row:
                raise KeyError(user_id)
            return _user_from_row(row)
        finally:
            conn.close()
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise KeyError(user_id)
        return _user_from_row(row)
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[User]:
    if using_postgres():
        conn = connect_postgres()
        try:
            row = conn.execute("SELECT * FROM users WHERE lower(email) = lower(%s)", (email,)).fetchone()
            if not row:
                return None
            return _user_from_row(row)
        finally:
            conn.close()
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE lower(email) = lower(?)", (email,)).fetchone()
        if not row:
            return None
        return _user_from_row(row)
    finally:
        conn.close()


def save_user(user: User) -> None:
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute(
                """
                INSERT INTO users (id, email, name, password_hash, created_at, updated_at, email_verified_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    email = EXCLUDED.email,
                    name = EXCLUDED.name,
                    password_hash = EXCLUDED.password_hash,
                    email_verified_at = EXCLUDED.email_verified_at,
                    updated_at = now()
                """,
                (user.id, user.email, user.name, user.password_hash, user.created_at, user.created_at, user.email_verified_at),
            )
            conn.commit()
        finally:
            conn.close()
        return
    conn = connect()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO users (id, email, name, password_hash, created_at, email_verified_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user.id, user.email, user.name, user.password_hash, user.created_at, user.email_verified_at),
        )
        conn.commit()
    finally:
        conn.close()


def create_session(user_id: str, created_at: str, expires_at: str) -> str:
    token = new_session_token()
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (%s, %s, %s, %s)",
                (token, user_id, created_at, expires_at),
            )
            conn.commit()
            return token
        finally:
            conn.close()
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
    if using_postgres():
        conn = connect_postgres()
        try:
            row = conn.execute(
                """
                SELECT users.*
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = %s AND sessions.expires_at > %s
                """,
                (token, now),
            ).fetchone()
            if not row:
                return None
            return _user_from_row(row)
        finally:
            conn.close()
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
        return _user_from_row(row)
    finally:
        conn.close()


def delete_session(token: str) -> None:
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute("DELETE FROM sessions WHERE token = %s", (token,))
            conn.commit()
        finally:
            conn.close()
        return
    conn = connect()
    try:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


def list_disputes(owner_id: str = DEMO_USER_ID) -> List[ConsumerDispute]:
    if using_postgres():
        conn = connect_postgres()
        try:
            return [
                _load_dataclass(ConsumerDispute, row["payload"])
                for row in conn.execute(
                    "SELECT payload FROM disputes WHERE owner_id = %s ORDER BY created_at DESC, id",
                    (owner_id,),
                ).fetchall()
            ]
        finally:
            conn.close()
    conn = connect()
    try:
        return [
            _load_dataclass(ConsumerDispute, row["payload"])
            for row in conn.execute("SELECT payload FROM disputes WHERE owner_id = ? ORDER BY id", (owner_id,)).fetchall()
        ]
    finally:
        conn.close()


def save_auth_token(auth_token: AuthToken) -> None:
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute(
                """
                INSERT INTO auth_tokens (token, user_id, purpose, created_at, expires_at, used_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (token) DO UPDATE SET used_at = EXCLUDED.used_at
                """,
                (
                    auth_token.token,
                    auth_token.user_id,
                    auth_token.purpose,
                    auth_token.created_at,
                    auth_token.expires_at,
                    auth_token.used_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO auth_tokens (token, user_id, purpose, created_at, expires_at, used_at) VALUES (?, ?, ?, ?, ?, ?)",
            (auth_token.token, auth_token.user_id, auth_token.purpose, auth_token.created_at, auth_token.expires_at, auth_token.used_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_auth_token(token: str, purpose: str, now: str) -> Optional[AuthToken]:
    if using_postgres():
        conn = connect_postgres()
        try:
            row = conn.execute(
                """
                SELECT * FROM auth_tokens
                WHERE token = %s AND purpose = %s AND used_at IS NULL AND expires_at > %s
                """,
                (token, purpose, now),
            ).fetchone()
            if not row:
                return None
            return AuthToken(
                token=row["token"],
                user_id=row["user_id"],
                purpose=row["purpose"],
                created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
                expires_at=row["expires_at"].isoformat() if hasattr(row["expires_at"], "isoformat") else row["expires_at"],
                used_at=row["used_at"].isoformat() if hasattr(row["used_at"], "isoformat") else row["used_at"],
            )
        finally:
            conn.close()
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM auth_tokens WHERE token = ? AND purpose = ? AND used_at IS NULL AND expires_at > ?",
            (token, purpose, now),
        ).fetchone()
        return AuthToken(**dict(row)) if row else None
    finally:
        conn.close()


def mark_auth_token_used(token: str, used_at: str) -> None:
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute("UPDATE auth_tokens SET used_at = %s WHERE token = %s", (used_at, token))
            conn.commit()
        finally:
            conn.close()
        return
    conn = connect()
    try:
        conn.execute("UPDATE auth_tokens SET used_at = ? WHERE token = ?", (used_at, token))
        conn.commit()
    finally:
        conn.close()


def update_user_password(user_id: str, password_hash: str) -> None:
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute("UPDATE users SET password_hash = %s, updated_at = now() WHERE id = %s", (password_hash, user_id))
            conn.commit()
        finally:
            conn.close()
        return
    conn = connect()
    try:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        conn.commit()
    finally:
        conn.close()


def mark_email_verified(user_id: str, verified_at: str) -> None:
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute(
                "UPDATE users SET email_verified_at = %s, updated_at = now() WHERE id = %s",
                (verified_at, user_id),
            )
            conn.commit()
        finally:
            conn.close()
        return
    conn = connect()
    try:
        conn.execute("UPDATE users SET email_verified_at = ? WHERE id = ?", (verified_at, user_id))
        conn.commit()
    finally:
        conn.close()


def get_dispute(dispute_id: str, owner_id: str = DEMO_USER_ID) -> ConsumerDispute:
    if using_postgres():
        conn = connect_postgres()
        try:
            row = conn.execute(
                "SELECT payload FROM disputes WHERE id = %s AND owner_id = %s",
                (dispute_id, owner_id),
            ).fetchone()
            if not row:
                raise KeyError(dispute_id)
            return _load_dataclass(ConsumerDispute, row["payload"])
        finally:
            conn.close()
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
    if using_postgres():
        conn = connect_postgres()
        try:
            _save_dispute_postgres(conn, dispute, owner_id)
            conn.commit()
        finally:
            conn.close()
        return
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
    if using_postgres():
        conn = connect_postgres()
        try:
            return [
                _load_dataclass(EvidenceArtifact, row["payload"])
                for row in conn.execute(
                    """
                    SELECT payload FROM evidence
                    WHERE dispute_id = %s AND owner_id = %s
                    ORDER BY occurred_at, id
                    """,
                    (dispute_id, owner_id),
                ).fetchall()
            ]
        finally:
            conn.close()
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
    if using_postgres():
        conn = connect_postgres()
        try:
            _save_evidence_postgres(conn, evidence, owner_id)
            conn.commit()
        finally:
            conn.close()
        return
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
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute(
                """
                INSERT INTO packets (id, dispute_id, owner_id, mode, status, validation_errors, payload, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    mode = EXCLUDED.mode,
                    status = EXCLUDED.status,
                    validation_errors = EXCLUDED.validation_errors,
                    payload = EXCLUDED.payload
                """,
                (
                    packet.id,
                    packet.dispute_id,
                    owner_id,
                    packet.mode,
                    packet.status,
                    _json_payload(packet.validation_errors),
                    _json_payload(asdict(packet)),
                    packet.created_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return
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
    if using_postgres():
        conn = connect_postgres()
        try:
            row = conn.execute(
                """
                SELECT payload FROM packets
                WHERE dispute_id = %s AND owner_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (dispute_id, owner_id),
            ).fetchone()
            return _load_packet(row["payload"]) if row else None
        finally:
            conn.close()
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
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute(
                """
                INSERT INTO outcomes (dispute_id, owner_id, outcome, note, payload, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (dispute_id) DO UPDATE SET
                    owner_id = EXCLUDED.owner_id,
                    outcome = EXCLUDED.outcome,
                    note = EXCLUDED.note,
                    payload = EXCLUDED.payload,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    outcome.dispute_id,
                    owner_id,
                    outcome.outcome,
                    outcome.note,
                    _json_payload(asdict(outcome)),
                    outcome.updated_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return
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
    if using_postgres():
        conn = connect_postgres()
        try:
            row = conn.execute(
                "SELECT payload FROM outcomes WHERE dispute_id = %s AND owner_id = %s",
                (dispute_id, owner_id),
            ).fetchone()
            return _load_outcome(row["payload"]) if row else None
        finally:
            conn.close()
    conn = connect()
    try:
        row = conn.execute(
            "SELECT payload FROM outcomes WHERE dispute_id = ? AND owner_id = ?",
            (dispute_id, owner_id),
        ).fetchone()
        return _load_outcome(row["payload"]) if row else None
    finally:
        conn.close()


def list_packets(owner_id: str) -> List[Packet]:
    if using_postgres():
        conn = connect_postgres()
        try:
            return [
                _load_packet(row["payload"])
                for row in conn.execute(
                    "SELECT payload FROM packets WHERE owner_id = %s ORDER BY created_at DESC",
                    (owner_id,),
                ).fetchall()
            ]
        finally:
            conn.close()
    conn = connect()
    try:
        return [
            _load_packet(row["payload"])
            for row in conn.execute(
                "SELECT payload FROM packets WHERE owner_id = ? ORDER BY json_extract(payload, '$.created_at') DESC",
                (owner_id,),
            ).fetchall()
        ]
    finally:
        conn.close()


def save_evidence_file(file: EvidenceFile) -> None:
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute(
                """
                INSERT INTO evidence_files (
                    id, evidence_id, dispute_id, owner_id, original_filename, content_type, size_bytes,
                    storage_bucket, storage_key, scan_status, extraction_status, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    original_filename = EXCLUDED.original_filename,
                    content_type = EXCLUDED.content_type,
                    size_bytes = EXCLUDED.size_bytes,
                    storage_bucket = EXCLUDED.storage_bucket,
                    storage_key = EXCLUDED.storage_key,
                    scan_status = EXCLUDED.scan_status,
                    extraction_status = EXCLUDED.extraction_status
                """,
                (
                    file.id,
                    file.evidence_id,
                    file.dispute_id,
                    file.owner_id,
                    file.original_filename,
                    file.content_type,
                    file.size_bytes,
                    file.storage_bucket,
                    file.storage_key,
                    file.scan_status,
                    file.extraction_status,
                    file.created_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO evidence_files (id, evidence_id, dispute_id, owner_id, payload) VALUES (?, ?, ?, ?, ?)",
            (file.id, file.evidence_id, file.dispute_id, file.owner_id, json.dumps(asdict(file))),
        )
        conn.commit()
    finally:
        conn.close()


def list_evidence_files(owner_id: str, dispute_id: Optional[str] = None) -> List[EvidenceFile]:
    if using_postgres():
        conn = connect_postgres()
        try:
            if dispute_id:
                rows = conn.execute(
                    """
                    SELECT * FROM evidence_files
                    WHERE owner_id = %s AND dispute_id = %s AND deleted_at IS NULL
                    ORDER BY created_at DESC
                    """,
                    (owner_id, dispute_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM evidence_files WHERE owner_id = %s AND deleted_at IS NULL ORDER BY created_at DESC",
                    (owner_id,),
                ).fetchall()
            return [
                EvidenceFile(
                    id=row["id"],
                    evidence_id=row["evidence_id"],
                    dispute_id=row["dispute_id"],
                    owner_id=row["owner_id"],
                    original_filename=row["original_filename"],
                    content_type=row["content_type"],
                    size_bytes=row["size_bytes"],
                    storage_bucket=row["storage_bucket"],
                    storage_key=row["storage_key"],
                    scan_status=row["scan_status"],
                    extraction_status=row["extraction_status"],
                    created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
                )
                for row in rows
            ]
        finally:
            conn.close()
    conn = connect()
    try:
        if dispute_id:
            rows = conn.execute(
                "SELECT payload FROM evidence_files WHERE owner_id = ? AND dispute_id = ?",
                (owner_id, dispute_id),
            ).fetchall()
        else:
            rows = conn.execute("SELECT payload FROM evidence_files WHERE owner_id = ?", (owner_id,)).fetchall()
        return [_load_evidence_file(row["payload"]) for row in rows]
    finally:
        conn.close()


def get_evidence_file(owner_id: str, file_id: str) -> Optional[EvidenceFile]:
    if using_postgres():
        conn = connect_postgres()
        try:
            row = conn.execute(
                "SELECT * FROM evidence_files WHERE owner_id = %s AND id = %s AND deleted_at IS NULL",
                (owner_id, file_id),
            ).fetchone()
            if not row:
                return None
            return EvidenceFile(
                id=row["id"],
                evidence_id=row["evidence_id"],
                dispute_id=row["dispute_id"],
                owner_id=row["owner_id"],
                original_filename=row["original_filename"],
                content_type=row["content_type"],
                size_bytes=row["size_bytes"],
                storage_bucket=row["storage_bucket"],
                storage_key=row["storage_key"],
                scan_status=row["scan_status"],
                extraction_status=row["extraction_status"],
                created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
            )
        finally:
            conn.close()
    conn = connect()
    try:
        row = conn.execute(
            "SELECT payload FROM evidence_files WHERE owner_id = ? AND id = ?",
            (owner_id, file_id),
        ).fetchone()
        return _load_evidence_file(row["payload"]) if row else None
    finally:
        conn.close()


def delete_evidence_file(owner_id: str, file_id: str, deleted_at: str) -> None:
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute(
                "UPDATE evidence_files SET deleted_at = %s WHERE owner_id = %s AND id = %s",
                (deleted_at, owner_id, file_id),
            )
            conn.commit()
        finally:
            conn.close()
        return
    conn = connect()
    try:
        conn.execute("DELETE FROM evidence_files WHERE owner_id = ? AND id = ?", (owner_id, file_id))
        conn.commit()
    finally:
        conn.close()


def list_outcomes(owner_id: str) -> List[OutcomeFeedback]:
    if using_postgres():
        conn = connect_postgres()
        try:
            return [
                _load_outcome(row["payload"])
                for row in conn.execute(
                    "SELECT payload FROM outcomes WHERE owner_id = %s ORDER BY updated_at DESC",
                    (owner_id,),
                ).fetchall()
            ]
        finally:
            conn.close()
    conn = connect()
    try:
        return [
            _load_outcome(row["payload"])
            for row in conn.execute("SELECT payload FROM outcomes WHERE owner_id = ?", (owner_id,)).fetchall()
        ]
    finally:
        conn.close()


def save_audit_log(entry: AuditLog) -> None:
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute(
                """
                INSERT INTO audit_logs (id, user_id, action, entity_type, entity_id, created_at, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    entry.id,
                    entry.user_id,
                    entry.action,
                    entry.entity_type,
                    entry.entity_id,
                    entry.created_at,
                    _json_payload(entry.metadata),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return
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
    if using_postgres():
        conn = connect_postgres()
        try:
            return [
                AuditLog(
                    id=row["id"],
                    user_id=row["user_id"],
                    action=row["action"],
                    entity_type=row["entity_type"],
                    entity_id=row["entity_id"],
                    created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
                    metadata=row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"]),
                )
                for row in conn.execute(
                    "SELECT * FROM audit_logs WHERE user_id = %s ORDER BY created_at DESC",
                    (user_id,),
                ).fetchall()
            ]
        finally:
            conn.close()
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


def save_background_job(job: BackgroundJob) -> None:
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute(
                """
                INSERT INTO background_jobs (
                    id, owner_id, job_type, status, attempts, payload, last_error, run_after, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    attempts = EXCLUDED.attempts,
                    payload = EXCLUDED.payload,
                    last_error = EXCLUDED.last_error,
                    run_after = EXCLUDED.run_after,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    job.id,
                    job.owner_id,
                    job.job_type,
                    job.status,
                    job.attempts,
                    _json_payload(job.payload),
                    job.last_error,
                    job.run_after,
                    job.created_at,
                    job.updated_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return
    conn = connect()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO background_jobs (
                id, owner_id, job_type, status, attempts, payload, last_error, run_after, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.id,
                job.owner_id,
                job.job_type,
                job.status,
                job.attempts,
                json.dumps(job.payload),
                job.last_error,
                job.run_after,
                job.created_at,
                job.updated_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_background_jobs(owner_id: str, limit: int = 20) -> List[BackgroundJob]:
    if using_postgres():
        conn = connect_postgres()
        try:
            return [
                BackgroundJob(
                    id=row["id"],
                    owner_id=row["owner_id"] or "",
                    job_type=row["job_type"],
                    status=row["status"],
                    attempts=row["attempts"],
                    payload=row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"]),
                    last_error=row["last_error"] or "",
                    run_after=row["run_after"].isoformat() if hasattr(row["run_after"], "isoformat") else row["run_after"],
                    created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
                    updated_at=row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else row["updated_at"],
                )
                for row in conn.execute(
                    "SELECT * FROM background_jobs WHERE owner_id = %s ORDER BY created_at DESC LIMIT %s",
                    (owner_id, limit),
                ).fetchall()
            ]
        finally:
            conn.close()
    conn = connect()
    try:
        return [
            BackgroundJob(
                id=row["id"],
                owner_id=row["owner_id"],
                job_type=row["job_type"],
                status=row["status"],
                attempts=row["attempts"],
                payload=json.loads(row["payload"]),
                last_error=row["last_error"],
                run_after=row["run_after"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in conn.execute(
                "SELECT * FROM background_jobs WHERE owner_id = ? ORDER BY created_at DESC LIMIT ?",
                (owner_id, limit),
            ).fetchall()
        ]
    finally:
        conn.close()


def get_queued_jobs(limit: int = 10) -> List[BackgroundJob]:
    if using_postgres():
        conn = connect_postgres()
        try:
            return [
                BackgroundJob(
                    id=row["id"],
                    owner_id=row["owner_id"] or "",
                    job_type=row["job_type"],
                    status=row["status"],
                    attempts=row["attempts"],
                    payload=row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"]),
                    last_error=row["last_error"] or "",
                    run_after=row["run_after"].isoformat() if hasattr(row["run_after"], "isoformat") else row["run_after"],
                    created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
                    updated_at=row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else row["updated_at"],
                )
                for row in conn.execute(
                    """
                    SELECT * FROM background_jobs
                    WHERE status = 'queued' AND run_after <= now()
                    ORDER BY run_after ASC
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            ]
        finally:
            conn.close()
    conn = connect()
    try:
        return [
            BackgroundJob(
                id=row["id"],
                owner_id=row["owner_id"],
                job_type=row["job_type"],
                status=row["status"],
                attempts=row["attempts"],
                payload=json.loads(row["payload"]),
                last_error=row["last_error"],
                run_after=row["run_after"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in conn.execute(
                """
                SELECT * FROM background_jobs
                WHERE status = 'queued'
                ORDER BY run_after ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]
    finally:
        conn.close()


def delete_account(user_id: str) -> None:
    if using_postgres():
        conn = connect_postgres()
        try:
            conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
        finally:
            conn.close()
        return
    conn = connect()
    try:
        for table in ("sessions", "auth_tokens", "outcomes", "packets", "evidence_files", "evidence", "disputes", "audit_logs"):
            key = "user_id" if table in {"sessions", "auth_tokens", "audit_logs"} else "owner_id"
            conn.execute(f"DELETE FROM {table} WHERE {key} = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
