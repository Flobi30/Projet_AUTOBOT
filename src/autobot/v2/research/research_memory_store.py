"""Append-only runtime storage for AUTOBOT research observations."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping


class ResearchMemoryStore:
    """SQLite-backed append-only research memory with idempotent writes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, record: Mapping[str, Any]) -> bool:
        payload = dict(record)
        self._validate_research_only(payload)
        run_id = str(payload.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("research memory record requires run_id")
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        content_hash = sha256(serialized.encode("utf-8")).hexdigest()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            self._initialize(connection)
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO research_memory_events
                    (run_id, recorded_at, record_json, content_hash)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, datetime.now(timezone.utc).isoformat(), serialized, content_hash),
            )
            return cursor.rowcount == 1

    def append_many(self, records: Iterable[Mapping[str, Any]]) -> int:
        return sum(1 for record in records if self.append(record))

    def latest_records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self._connect() as connection:
            self._initialize(connection)
            rows = connection.execute(
                """
                SELECT event.record_json
                FROM research_memory_events AS event
                JOIN (
                    SELECT run_id, MAX(event_id) AS event_id
                    FROM research_memory_events
                    GROUP BY run_id
                ) AS latest ON latest.event_id = event.event_id
                ORDER BY event.event_id
                """
            ).fetchall()
        return [json.loads(str(row[0])) for row in rows]

    def event_count(self) -> int:
        if not self.path.exists():
            return 0
        with self._connect() as connection:
            self._initialize(connection)
            return int(connection.execute("SELECT COUNT(*) FROM research_memory_events").fetchone()[0])

    def export_latest(self, destination: str | Path) -> Path:
        """Write a compact, deterministic research-only export for review.

        The SQLite event store remains the runtime source of truth.  This
        export is deliberately a snapshot for audit or source-control review,
        never a mutable runtime sink.
        """
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "promotable": False,
            "source_event_count": self.event_count(),
            "records": self.latest_records(),
        }
        target.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str) + "\n",
            encoding="utf-8",
        )
        return target

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS research_memory_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                record_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                UNIQUE(run_id, content_hash)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_research_memory_events_run ON research_memory_events(run_id, event_id)"
        )

    @staticmethod
    def _validate_research_only(record: Mapping[str, Any]) -> None:
        if any(bool(record.get(field)) for field in ("paper_capital_allowed", "live_allowed", "promotable")):
            raise ValueError("research memory events cannot enable paper/live/promotion")
