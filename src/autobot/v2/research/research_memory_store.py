"""Append-only runtime storage for AUTOBOT research observations."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
from pathlib import Path
import sqlite3
from time import sleep
from typing import Any, Callable, Iterable, Mapping, TypeVar


logger = logging.getLogger(__name__)
_T = TypeVar("_T")


class ResearchMemoryStore:
    """SQLite-backed append-only research memory with idempotent writes."""

    def __init__(
        self,
        path: str | Path,
        *,
        sqlite_timeout_seconds: float = 30.0,
        write_retries: int = 3,
        retry_base_delay_seconds: float = 0.05,
        sleeper: Callable[[float], None] = sleep,
        read_only: bool = False,
    ) -> None:
        self.path = Path(path)
        if sqlite_timeout_seconds <= 0.0 or write_retries < 0 or retry_base_delay_seconds < 0.0:
            raise ValueError("invalid research-memory SQLite retry configuration")
        self._sqlite_timeout_seconds = float(sqlite_timeout_seconds)
        self._busy_timeout_ms = max(1, int(self._sqlite_timeout_seconds * 1000))
        self._write_retries = int(write_retries)
        self._retry_base_delay_seconds = float(retry_base_delay_seconds)
        self._sleeper = sleeper
        self._read_only = bool(read_only)

    def append(self, record: Mapping[str, Any]) -> bool:
        if self._read_only:
            raise PermissionError("research memory store is read-only")
        payload = dict(record)
        self._validate_research_only(payload)
        run_id = str(payload.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("research memory record requires run_id")
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        content_hash = sha256(serialized.encode("utf-8")).hexdigest()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(self._write_retries + 1):
            try:
                inserted = self._append_once(run_id=run_id, serialized=serialized, content_hash=content_hash)
                # A busy commit has uncertain acknowledgement semantics. If a
                # retry observes the idempotency key, the desired append is
                # durable and should still be reported as successful.
                return inserted or attempt > 0
            except sqlite3.OperationalError as exc:
                if not _is_transient_lock(exc) or attempt >= self._write_retries:
                    raise
                delay = self._retry_base_delay_seconds * (2 ** attempt)
                logger.warning(
                    "Research-memory SQLite busy during append; retry %s/%s in %.3fs",
                    attempt + 1,
                    self._write_retries,
                    delay,
                )
                self._sleeper(delay)

        raise AssertionError("unreachable research-memory SQLite retry state")

    def append_many(self, records: Iterable[Mapping[str, Any]]) -> int:
        return sum(1 for record in records if self.append(record))

    def latest_records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self._connect() as connection:
            if not self._read_only:
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
            if not self._read_only:
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
        if self._read_only:
            if not self.path.is_file():
                raise FileNotFoundError(f"research memory SQLite database is unavailable: {self.path}")
            connection = sqlite3.connect(
                f"{self.path.resolve().as_uri()}?mode=ro",
                uri=True,
                timeout=self._sqlite_timeout_seconds,
            )
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            return connection
        connection = sqlite3.connect(self.path, timeout=self._sqlite_timeout_seconds)
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        return connection

    def _append_once(self, *, run_id: str, serialized: str, content_hash: str) -> bool:
        connection = self._connect()
        try:
            self._initialize(connection)
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO research_memory_events
                    (run_id, recorded_at, record_json, content_hash)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, datetime.now(timezone.utc).isoformat(), serialized, content_hash),
            )
            connection.commit()
            return cursor.rowcount == 1
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

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


def _is_transient_lock(error: sqlite3.OperationalError) -> bool:
    message = str(error).lower()
    return "locked" in message or "busy" in message
