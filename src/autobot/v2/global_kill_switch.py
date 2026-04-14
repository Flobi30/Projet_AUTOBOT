from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class GlobalKillState:
    tripped: bool
    reason_code: Optional[str]
    reason: Optional[str]
    tripped_at: Optional[str]
    recovery_required: bool


class GlobalKillSwitchStore:
    """Cross-process kill-switch state persistence."""

    def __init__(self, db_path: str = "data/global_kill_switch.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
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

    def get(self) -> GlobalKillState:
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT tripped, reason_code, reason, tripped_at, recovery_required FROM global_kill_state WHERE id=1"
            ).fetchone()
        return GlobalKillState(
            tripped=bool(row[0]),
            reason_code=row[1],
            reason=row[2],
            tripped_at=row[3],
            recovery_required=bool(row[4]),
        )

    def trip(self, reason_code: str, reason: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
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

    def acknowledge_recovery(self, operator_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                UPDATE global_kill_state
                SET tripped=0, recovery_required=0, recovery_ack_by=?, recovery_ack_at=?
                WHERE id=1
                """,
                (operator_id, now),
            )
            conn.commit()

