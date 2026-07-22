from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
from typing import Callable, Optional, TypeVar


logger = logging.getLogger(__name__)
_T = TypeVar("_T")


class GlobalKillSwitchStoreError(RuntimeError):
    """Raised when persisted recovery acknowledgement cannot be made safely."""


@dataclass
class GlobalKillState:
    tripped: bool
    reason_code: Optional[str]
    reason: Optional[str]
    tripped_at: Optional[str]
    recovery_required: bool
    storage_healthy: bool = True
    storage_error: Optional[str] = None


class GlobalKillSwitchStore:
    """Cross-process kill-switch state persistence with fail-closed reads."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        *,
        sqlite_timeout_seconds: float = 0.25,
        retry_attempts: int = 3,
        retry_delay_seconds: float = 0.05,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.db_path = Path(
            db_path
            or os.getenv("GLOBAL_KILL_SWITCH_DB_PATH", "data/global_kill_switch.db")
        )
        if sqlite_timeout_seconds <= 0.0 or retry_attempts < 1 or retry_delay_seconds < 0.0:
            raise ValueError("invalid global kill-switch SQLite retry configuration")
        self._sqlite_timeout_seconds = float(sqlite_timeout_seconds)
        self._busy_timeout_ms = max(1, int(self._sqlite_timeout_seconds * 1000))
        self._retry_attempts = int(retry_attempts)
        self._retry_delay_seconds = float(retry_delay_seconds)
        self._sleeper = sleeper
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        def initialize() -> None:
            with self._connect() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS global_kill_state (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        tripped INTEGER NOT NULL,
                        reason_code TEXT,
                        reason TEXT,
                        tripped_at TEXT,
                        recovery_required INTEGER NOT NULL DEFAULT 1,
                        recovery_ack_by TEXT,
                        recovery_ack_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO global_kill_state (id, tripped, recovery_required)
                    VALUES (1, 0, 0)
                    ON CONFLICT(id) DO NOTHING
                    """
                )
                conn.commit()

        self._run_sqlite(initialize, operation_name="initialize")

    def get(self) -> GlobalKillState:
        """Read the global state; unreadable persistence means globally tripped."""

        try:
            row = self._run_sqlite(self._read_persisted_state, operation_name="read")
        except GlobalKillSwitchStoreError as exc:
            logger.critical("Global kill-switch state unavailable; failing closed: %s", exc)
            return GlobalKillState(
                tripped=True,
                reason_code="kill_switch_store_unavailable",
                reason="persistent kill-switch state could not be read",
                tripped_at=None,
                recovery_required=True,
                storage_healthy=False,
                storage_error=str(exc),
            )
        if row is None:
            logger.critical("Global kill-switch state row missing; failing closed")
            return GlobalKillState(
                tripped=True,
                reason_code="kill_switch_store_invalid",
                reason="persistent kill-switch state row is missing",
                tripped_at=None,
                recovery_required=True,
                storage_healthy=False,
                storage_error="state_row_missing",
            )
        return GlobalKillState(
            tripped=bool(row[0]),
            reason_code=row[1],
            reason=row[2],
            tripped_at=row[3],
            recovery_required=bool(row[4]),
        )

    def trip(self, reason_code: str, reason: str) -> bool:
        """Persist a global trip when possible; callers remain locally tripped otherwise."""

        now = datetime.now(timezone.utc).isoformat()

        def write_trip() -> None:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE global_kill_state
                    SET tripped=1, reason_code=?, reason=?, tripped_at=?, recovery_required=1,
                        recovery_ack_by=NULL, recovery_ack_at=NULL
                    WHERE id=1
                    """,
                    (reason_code, reason, now),
                )
                conn.commit()

        try:
            self._run_sqlite(write_trip, operation_name="trip")
            return True
        except GlobalKillSwitchStoreError as exc:
            logger.critical("Global kill-switch trip persistence failed; local halt remains active: %s", exc)
            return False

    def acknowledge_recovery(self, operator_id: str) -> None:
        """Clear persistence only when its write is confirmed; never fail open."""

        now = datetime.now(timezone.utc).isoformat()

        def acknowledge() -> None:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE global_kill_state
                    SET tripped=0, recovery_required=0, recovery_ack_by=?, recovery_ack_at=?
                    WHERE id=1
                    """,
                    (operator_id, now),
                )
                conn.commit()

        self._run_sqlite(acknowledge, operation_name="acknowledge")

    def _read_persisted_state(self) -> tuple[object, object, object, object, object] | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT tripped, reason_code, reason, tripped_at, recovery_required FROM global_kill_state WHERE id=1"
            ).fetchone()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=self._sqlite_timeout_seconds)
        connection.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
        return connection

    def _run_sqlite(self, operation: Callable[[], _T], *, operation_name: str = "") -> _T:
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return operation()
            except sqlite3.OperationalError as exc:
                if not _is_transient_lock(exc) or attempt >= self._retry_attempts:
                    raise GlobalKillSwitchStoreError(
                        f"global kill-switch {operation_name or 'database'} operation failed: {type(exc).__name__}"
                    ) from exc
                self._sleeper(self._retry_delay_seconds * attempt)
            except sqlite3.DatabaseError as exc:
                raise GlobalKillSwitchStoreError(
                    f"global kill-switch {operation_name or 'database'} operation failed: {type(exc).__name__}"
                ) from exc
        raise AssertionError("unreachable SQLite retry state")


def _is_transient_lock(error: sqlite3.OperationalError) -> bool:
    message = str(error).lower()
    return "locked" in message or "busy" in message

