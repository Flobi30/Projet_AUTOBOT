from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path


class NonceManager:
    """Process-safe monotonic nonce generator shared through SQLite."""

    def __init__(self, db_path: str = "data/nonce_state.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
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
        now_ms = int(time.time() * 1000)
        with self._lock, sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
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
