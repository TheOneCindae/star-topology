"""Experiment snapshots and honest CSV export."""

import csv
from pathlib import Path
from typing import Any

from storage.database import Database


def export_csv(database: Database, destination: str | Path) -> Path:
    rows = database.events(limit=2**31 - 1)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "timestamp", "kind", "payload"])
        writer.writeheader()
        writer.writerows(rows)
    return path


class ExperimentStore(Database):
    """Named facade retained for experiment-oriented callers."""

    def record(self, kind: str, **payload: Any) -> int:
        return self.record_event(kind, payload)

    def export_csv(self, destination: str | Path) -> Path:
        return export_csv(self, destination)
