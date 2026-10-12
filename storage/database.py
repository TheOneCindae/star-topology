"""Small SQLite event/statistics store used by the server and dashboard."""

import json
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
        self.connection.commit()

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
