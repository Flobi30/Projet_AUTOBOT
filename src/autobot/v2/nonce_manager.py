from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path


class NonceManager:
    """Process-safe monotonic nonce generator shared through SQLite."""

    _BUSY_TIMEOUT_SECONDS = 30.0
    _BUSY_RETRY_COUNT = 6
    _BUSY_RETRY_BASE_SECONDS = 0.025

    def __init__(self, db_path: str = "data/nonce_state.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._retry_busy(self._init_db_once)

    def _init_db_once(self) -> None:
        with sqlite3.connect(str(self.db_path), timeout=self._BUSY_TIMEOUT_SECONDS) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(f"PRAGMA busy_timeout={int(self._BUSY_TIMEOUT_SECONDS * 1000)}")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nonce_state (
                    api_key_id TEXT PRIMARY KEY,
                    last_nonce INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()

    @staticmethod
    def _is_busy_error(exc: sqlite3.OperationalError) -> bool:
        message = str(exc).lower()
        return "database is locked" in message or "database is busy" in message

    def _retry_busy(self, operation):
        """Retry only bounded, transient SQLite writer contention.

        Nonce reservation is idempotent until its commit succeeds.  Retrying a
        failed ``BEGIN IMMEDIATE`` therefore cannot emit an already committed
        nonce range, while a finite backoff keeps exchange execution from
        waiting forever on a damaged database.
        """
        for attempt in range(self._BUSY_RETRY_COUNT + 1):
            try:
                return operation()
            except sqlite3.OperationalError as exc:
                if not self._is_busy_error(exc) or attempt >= self._BUSY_RETRY_COUNT:
                    raise
                time.sleep(self._BUSY_RETRY_BASE_SECONDS * (2 ** attempt))
        raise RuntimeError("unreachable SQLite retry state")

    def next_nonce(self, api_key_id: str) -> int:
        low, _high = self.reserve_range(api_key_id, block_size=1)
        return int(low)

    def reserve_range(self, api_key_id: str, block_size: int = 64) -> tuple[int, int]:
        """
        Reserve a contiguous nonce range in a single durable write.

        Returns:
            (low, high) inclusive range.
        """
        if not api_key_id:
            raise ValueError("api_key_id is required")
        if block_size <= 0:
            raise ValueError("block_size must be > 0")
        with self._lock:
            return self._retry_busy(lambda: self._reserve_range_once(api_key_id, block_size))

    def _reserve_range_once(self, api_key_id: str, block_size: int) -> tuple[int, int]:
        now_ms = int(time.time() * 1000)
        with sqlite3.connect(str(self.db_path), timeout=self._BUSY_TIMEOUT_SECONDS) as conn:
            conn.execute(f"PRAGMA busy_timeout={int(self._BUSY_TIMEOUT_SECONDS * 1000)}")
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT last_nonce FROM nonce_state WHERE api_key_id = ?",
                (api_key_id,),
            ).fetchone()
            if row:
                low = max(int(row[0]) + 1, now_ms)
                high = low + block_size - 1
                conn.execute(
                    "UPDATE nonce_state SET last_nonce = ?, updated_at = datetime('now') WHERE api_key_id = ?",
                    (high, api_key_id),
                )
            else:
                low = now_ms
                high = low + block_size - 1
                conn.execute(
                    "INSERT INTO nonce_state (api_key_id, last_nonce) VALUES (?, ?)",
                    (api_key_id, high),
                )
            conn.commit()
            return int(low), int(high)
