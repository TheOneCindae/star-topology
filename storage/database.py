"""Small SQLite event/statistics store used by the server and dashboard."""

import json
import hashlib
import hmac
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional


class Database:
    def __init__(self, path: str | Path = "data/star_topology.sqlite3") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL,
            kind TEXT NOT NULL, payload TEXT NOT NULL)""")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                credential_salt BLOB NOT NULL,
                credential_hash BLOB NOT NULL,
                last_seen REAL
            );
            CREATE TABLE IF NOT EXISTS permissions (
                source_id INTEGER NOT NULL,
                destination_id INTEGER NOT NULL,
                message_type INTEGER NOT NULL,
                allowed INTEGER NOT NULL,
                PRIMARY KEY (source_id, destination_id, message_type)
            );
            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                destination_id INTEGER NOT NULL,
                message_type INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                status TEXT NOT NULL,
                reason TEXT
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        self.connection.commit()

    @staticmethod
    def _hash_credential(credential: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256", credential.encode("utf-8"), salt, 120_000
        )

    def provision_node(self, node_id: int, name: str | None = None) -> str:
        credential = secrets.token_urlsafe(24)
        salt = secrets.token_bytes(16)
        digest = self._hash_credential(credential, salt)
        self.connection.execute(
            """INSERT INTO nodes(node_id,name,status,credential_salt,credential_hash)
               VALUES (?, ?, 'active', ?, ?)
               ON CONFLICT(node_id) DO UPDATE SET name=excluded.name,
               status='active', credential_salt=excluded.credential_salt,
               credential_hash=excluded.credential_hash""",
            (node_id, name or f"Node {node_id}", salt, digest),
        )
        self.connection.commit()
        return credential

    def authenticate_node(self, node_id: int, credential: str) -> bool:
        row = self.connection.execute(
            "SELECT status,credential_salt,credential_hash FROM nodes WHERE node_id=?",
            (node_id,),
        ).fetchone()
        if row is None or row["status"] != "active":
            return False
        digest = self._hash_credential(credential, row["credential_salt"])
        valid = hmac.compare_digest(digest, row["credential_hash"])
        if valid:
            self.connection.execute(
                "UPDATE nodes SET last_seen=? WHERE node_id=?", (time.time(), node_id)
            )
            self.connection.commit()
        return valid

    def set_node_status(self, node_id: int, status: str) -> None:
        if status not in {"active", "revoked", "inactive"}:
            raise ValueError("status must be active, revoked, or inactive")
        cur = self.connection.execute(
            "UPDATE nodes SET status=? WHERE node_id=?", (status, node_id)
        )
        if cur.rowcount == 0:
            raise KeyError(f"Unknown node {node_id}")
        self.connection.commit()

    def node_is_active(self, node_id: int) -> bool:
        row = self.connection.execute(
            "SELECT status FROM nodes WHERE node_id=?", (node_id,)
        ).fetchone()
        return row is not None and row["status"] == "active"

    def nodes(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT node_id,name,status,last_seen FROM nodes ORDER BY node_id"
        ).fetchall()
        return [dict(row) for row in rows]

    def set_permission(
        self, source_id: int, destination_id: int, message_type: int, allowed: bool
    ) -> None:
        self.connection.execute(
            """INSERT INTO permissions(source_id,destination_id,message_type,allowed)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(source_id,destination_id,message_type)
               DO UPDATE SET allowed=excluded.allowed""",
            (source_id, destination_id, message_type, int(allowed)),
        )
        self.connection.commit()

    def permission(self, source_id: int, destination_id: int, message_type: int) -> bool:
        row = self.connection.execute(
            """SELECT allowed FROM permissions
               WHERE source_id=? AND destination_id=? AND message_type=?""",
            (source_id, destination_id, message_type),
        ).fetchone()
        return row is None or bool(row["allowed"])

    def record_message(
        self, source_id: int, destination_id: int, message_type: int,
        status: str, reason: str = ""
    ) -> int:
        cur = self.connection.execute(
            """INSERT INTO messages(source_id,destination_id,message_type,timestamp,status,reason)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (source_id, destination_id, message_type, time.time(), status, reason),
        )
        self.connection.commit()
        return int(cur.lastrowid)

    def record_audit(
        self, actor: str, action: str, decision: str, reason: str
    ) -> int:
        cur = self.connection.execute(
            """INSERT INTO audit_logs(timestamp,actor,action,decision,reason)
               VALUES (?, ?, ?, ?, ?)""",
            (time.time(), actor, action, decision, reason),
        )
        self.connection.commit()
        return int(cur.lastrowid)

    def permissions(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT source_id,destination_id,message_type,allowed FROM permissions "
            "ORDER BY source_id,destination_id,message_type"
        ).fetchall()
        return [dict(row) for row in rows]

    def messages(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """SELECT message_id,source_id,destination_id,message_type,timestamp,status,reason
               FROM messages ORDER BY message_id DESC LIMIT ?""",
            (max(1, min(limit, 1000)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def audits(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """SELECT id,timestamp,actor,action,decision,reason
               FROM audit_logs ORDER BY id DESC LIMIT ?""",
            (max(1, min(limit, 1000)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def record_event(self, kind: str, payload: dict[str, Any]) -> int:
        cur = self.connection.execute(
            "INSERT INTO events(timestamp, kind, payload) VALUES (?, ?, ?)",
            (time.time(), kind, json.dumps(payload, sort_keys=True)))
        self.connection.commit()
        return int(cur.lastrowid)

    def events(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT id,timestamp,kind,payload FROM events ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def stats(self) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT kind, COUNT(*) AS count FROM events GROUP BY kind").fetchall()
        return {row["kind"]: row["count"] for row in rows}

    def close(self) -> None:
        self.connection.close()
