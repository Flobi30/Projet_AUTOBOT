"""
Persistence - Sauvegarde et récupération d'état SQLite (Asynchrone via aiosqlite)
ARCH-03: Migration vers aiosqlite pour éviter les blocages du loop asyncio.
"""

import logging
import os
import sqlite3
import aiosqlite
import orjson
import hashlib
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path

from .strategy_runtime_policy import (
    EXECUTION_MODE_LEGACY_UNSPECIFIED,
    LEGACY_UNATTRIBUTED_STRATEGY_ID,
    normalize_execution_mode,
    official_paper_strategy_block_reason,
    trade_ledger_append_block_reason,
)

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


class _PersistenceRepositoryBase:
    """Shared helpers for aiosqlite repositories."""

    def __init__(self, db_path: Path, write_lock: Optional[asyncio.Lock] = None):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._conn_lock = asyncio.Lock()
        self._write_lock = write_lock or asyncio.Lock()

    @property
    def _busy_timeout_ms(self) -> int:
        return _env_int("SQLITE_BUSY_TIMEOUT_MS", 30_000, 1_000, 300_000)

    @property
    def _write_retries(self) -> int:
        return _env_int("SQLITE_WRITE_RETRIES", 5, 0, 50)

    @property
    def _retry_base_delay_ms(self) -> int:
        return _env_int("SQLITE_RETRY_BASE_DELAY_MS", 50, 1, 10_000)

    async def get_conn(self) -> aiosqlite.Connection:
        async with self._conn_lock:
            if self._conn is None:
                self._conn = await aiosqlite.connect(
                    str(self.db_path),
                    timeout=self._busy_timeout_ms / 1000.0,
                )
                self._conn.row_factory = aiosqlite.Row
                await self._conn.execute("PRAGMA journal_mode=WAL")
                await self._conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
                await self._conn.execute("PRAGMA synchronous=NORMAL")
            return self._conn

    @staticmethod
    def _is_busy_error(exc: Exception) -> bool:
        if not isinstance(exc, sqlite3.OperationalError):
            return False
        message = str(exc).lower()
        return "database is locked" in message or "database is busy" in message

    async def _with_write_retries(self, label: str, operation):
        last_exc: Optional[Exception] = None
        for attempt in range(self._write_retries + 1):
            try:
                async with self._write_lock:
                    return await operation()
            except Exception as exc:
                if not self._is_busy_error(exc) or attempt >= self._write_retries:
                    raise
                last_exc = exc
                delay = (self._retry_base_delay_ms / 1000.0) * (2 ** attempt)
                logger.warning(
                    "SQLite busy during %s; retry %s/%s in %.3fs",
                    label,
                    attempt + 1,
                    self._write_retries,
                    delay,
                )
                await asyncio.sleep(delay)
        if last_exc is not None:
            raise last_exc

    async def close(self):
        async with self._conn_lock:
            if self._conn:
                await self._conn.close()
                self._conn = None


class OrderRepository(_PersistenceRepositoryBase):
    """Order lifecycle persistence (orders + transitions)."""

    async def upsert_order(
        self,
        client_order_id: str,
        instance_id: str,
        symbol: str,
        side: str,
        order_type: str,
        requested_qty: float,
        status: str = "NEW",
        userref: Optional[int] = None,
        decision_id: Optional[str] = None,
        signal_id: Optional[str] = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = await self.get_conn()
            await conn.execute(
                """
                INSERT INTO orders
                (client_order_id, decision_id, signal_id, instance_id, symbol, side, order_type,
                 requested_qty, status, userref, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_order_id) DO UPDATE SET
                    decision_id=excluded.decision_id,
                    signal_id=excluded.signal_id,
                    instance_id=excluded.instance_id,
                    symbol=excluded.symbol,
                    side=excluded.side,
                    order_type=excluded.order_type,
                    requested_qty=excluded.requested_qty,
                    userref=excluded.userref,
                    updated_at=excluded.updated_at
                """,
                (
                    client_order_id, decision_id, signal_id, instance_id, symbol, side, order_type,
                    requested_qty, status, userref, now, now,
                ),
            )
            await conn.commit()
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur upsert_order {client_order_id}: {e}")
            return False

    async def transition_order_state(
        self,
        client_order_id: str,
        to_status: str,
        reason: str,
        source: str,
        exchange_order_id: Optional[str] = None,
        filled_qty: Optional[float] = None,
        avg_fill_price: Optional[float] = None,
        userref: Optional[int] = None,
        retries_delta: int = 0,
        last_error_code: Optional[str] = None,
        last_error_message: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        try:
            async def _write() -> bool:
                conn = await self.get_conn()
                async with conn.execute(
                    "SELECT status FROM orders WHERE client_order_id = ?",
                    (client_order_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                if row is None or row[0] is None or not str(row[0]).strip():
                    logger.warning("Order transition rejected: missing prior order state (client_order_id=%s)", client_order_id)
                    return False
                from_status = str(row[0]).strip()

                # Update the order and append its transition under the same
                # serialized write boundary. Existing legacy rows are never
                # rewritten; this only improves new transition evidence.
                updates = ["updated_at = ?", "status = ?", "retries = retries + ?"]
                params = [now, to_status, retries_delta]
                if exchange_order_id:
                    updates.append("exchange_order_id = ?")
                    params.append(exchange_order_id)
                if filled_qty is not None:
                    updates.append("filled_qty = ?")
                    params.append(filled_qty)
                if avg_fill_price is not None:
                    updates.append("avg_fill_price = ?")
                    params.append(avg_fill_price)
                if last_error_code:
                    updates.append("last_error_code = ?")
                    params.append(last_error_code)
                if last_error_message:
                    updates.append("last_error_message = ?")
                    params.append(last_error_message)
                if to_status == "SENT":
                    updates.append("sent_at = ?")
                    params.append(now)
                if to_status == "ACK":
                    updates.append("ack_at = ?")
                    params.append(now)
                if to_status in {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}:
                    updates.append("terminal_at = ?")
                    params.append(now)

                params.append(client_order_id)
                query = f"UPDATE orders SET {', '.join(updates)} WHERE client_order_id = ?"
                update_cursor = await conn.execute(query, tuple(params))
                if int(update_cursor.rowcount or 0) != 1:
                    logger.warning("Order transition rejected: order update was not unique (client_order_id=%s)", client_order_id)
                    return False

                payload_json = orjson.dumps(payload).decode() if payload else None
                await conn.execute(
                    """
                    INSERT INTO order_state_transitions
                    (client_order_id, from_status, to_status, reason, source, payload_hash, occurred_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (client_order_id, from_status, to_status, reason, source, payload_json, now),
                )
                await conn.commit()
                return True

            return await self._with_write_retries("transition_order_state", _write)
        except Exception as e:
            logger.exception(f"❌ Erreur transition_order_state {client_order_id} -> {to_status}: {e}")
            return False

    async def get_order(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        try:
            conn = await self.get_conn()
            async with conn.execute("SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.exception(f"❌ Erreur get_order {client_order_id}: {e}")
            return None

    async def get_non_terminal_orders(self) -> List[Dict[str, Any]]:
        try:
            conn = await self.get_conn()
            async with conn.execute(
                """
                SELECT * FROM orders
                WHERE status NOT IN ('FILLED', 'CANCELED', 'REJECTED', 'EXPIRED')
                  AND terminal_at IS NULL
                """
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.exception(f"❌ Erreur get_non_terminal_orders: {e}")
            return []


class AuditRepository(_PersistenceRepositoryBase):
    """Immutable audit trail with hash-chaining."""

    async def append_audit_event(
        self,
        event_id: str,
        event_type: str,
        instance_id: str,
        config_hash: str,
        risk_snapshot: Dict[str, Any],
        decision_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
        balance_before: Optional[Dict[str, Any]] = None,
        balance_after: Optional[Dict[str, Any]] = None,
        fees: Optional[float] = None,
        slippage_bps: Optional[float] = None,
        order_from_status: Optional[str] = None,
        order_to_status: Optional[str] = None,
        exchange_raw_normalized: Optional[Dict[str, Any]] = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = await self.get_conn()
            # Get previous hash
            async with conn.execute("SELECT event_hash FROM audit_events ORDER BY created_at DESC LIMIT 1") as cursor:
                prev_row = await cursor.fetchone()
                prev_hash = prev_row["event_hash"] if prev_row else "0" * 64

            risk_json = orjson.dumps(risk_snapshot).decode()
            bal_b_json = orjson.dumps(balance_before).decode() if balance_before else None
            bal_a_json = orjson.dumps(balance_after).decode() if balance_after else None
            raw_json = orjson.dumps(exchange_raw_normalized).decode() if exchange_raw_normalized else None

            # Simple hash chaining
            payload = f"{prev_hash}{event_id}{event_type}{instance_id}{now}"
            event_hash = hashlib.sha256(payload.encode()).hexdigest()

            await conn.execute(
                """
                INSERT INTO audit_events
                (event_id, event_type, decision_id, signal_id, client_order_id, exchange_order_id,
                 instance_id, config_hash, risk_snapshot, balance_before, balance_after,
                 fees, slippage_bps, order_from_status, order_to_status,
                 exchange_raw_normalized, prev_event_hash, event_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, event_type, decision_id, signal_id, client_order_id, exchange_order_id,
                    instance_id, config_hash, risk_json, bal_b_json, bal_a_json,
                    fees, slippage_bps, order_from_status, order_to_status,
                    raw_json, prev_hash, event_hash, now,
                ),
            )
            await conn.commit()
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur append_audit_event {event_id}: {e}")
            return False

    async def get_execution_fee(self, instance_id: str, exchange_order_id: str) -> Optional[float]:
        try:
            conn = await self.get_conn()
            async with conn.execute(
                """
                SELECT fees FROM audit_events
                WHERE instance_id = ? AND exchange_order_id = ? AND fees IS NOT NULL
                ORDER BY created_at DESC LIMIT 1
                """,
                (instance_id, exchange_order_id),
            ) as cursor:
                row = await cursor.fetchone()
                return float(row["fees"]) if row else None
        except Exception as e:
            logger.exception(f"❌ Erreur get_execution_fee {instance_id}/{exchange_order_id}: {e}")
            return None


class PositionRepository(_PersistenceRepositoryBase):
    """Position state persistence."""

    async def save_position(self, position_id: str, instance_id: str,
                      buy_price: float, volume: float,
                      status: str = "open", strategy: str = "",
                      metadata: Optional[Dict] = None,
                      symbol: Optional[str] = None) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = await self.get_conn()
            metadata = dict(metadata or {})
            if symbol is None:
                symbol = metadata.get("symbol")
            elif "symbol" not in metadata:
                metadata["symbol"] = symbol
            normalized_symbol = str(symbol or "").strip().upper() or None
            meta_json = orjson.dumps(metadata).decode() if metadata else None
            await conn.execute(
                """
                INSERT INTO positions (id, instance_id, symbol, buy_price, volume, status, open_time, strategy, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (position_id, instance_id, normalized_symbol, buy_price, volume, status, now, strategy, meta_json)
            )
            await conn.commit()
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur sauvegarde position {position_id}: {e}")
            return False

    async def update_position_status(self, position_id: str, status: str) -> bool:
        try:
            conn = await self.get_conn()
            await conn.execute("UPDATE positions SET status = ? WHERE id = ?", (status, position_id))
            await conn.commit()
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur update_position_status {position_id}: {e}")
            return False

    async def close_position_and_record_trade(self, position_id: str, trade_data: Dict[str, Any]) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = await self.get_conn()
            # Atomique : update position + insert trade
            await conn.execute("UPDATE positions SET status = 'closed' WHERE id = ?", (position_id,))
            await conn.execute(
                """
                INSERT INTO trades (position_id, instance_id, side, price, volume, profit, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position_id, trade_data['instance_id'], 'sell', trade_data['price'],
                    trade_data['volume'], trade_data.get('profit'), now
                )
            )
            await conn.commit()
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur close_position_and_record_trade {position_id}: {e}")
            return False

    async def recover_positions(self, instance_id: str, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            conn = await self.get_conn()
            if symbol:
                query = """
                    SELECT DISTINCT p.*
                    FROM positions p
                    LEFT JOIN trade_ledger tl
                      ON tl.position_id = p.id
                     AND COALESCE(tl.is_opening_leg, 1) = 1
                    WHERE p.status = 'open'
                      AND (
                        p.instance_id = ?
                        OR UPPER(COALESCE(p.symbol, '')) = UPPER(?)
                        OR UPPER(COALESCE(json_extract(p.metadata, '$.symbol'), '')) = UPPER(?)
                        OR UPPER(COALESCE(tl.symbol, '')) = UPPER(?)
                      )
                """
                args = (instance_id, symbol, symbol, symbol)
            else:
                query = "SELECT * FROM positions WHERE instance_id = ? AND status = 'open'"
                args = (instance_id,)
            async with conn.execute(query, args) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.exception(f"❌ Erreur recover_positions {instance_id}: {e}")
            return []


class InstanceStateRepository(_PersistenceRepositoryBase):
    """Instance state persistence."""

    async def save_instance_state(self, instance_id: str, status: str,
                            current_capital: float, allocated_capital: float,
                            win_count: int, loss_count: int,
                            initial_capital: Optional[float] = None) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = await self.get_conn()
            await conn.execute(
                """
                INSERT INTO instance_state (instance_id, status, current_capital, allocated_capital, win_count, loss_count, initial_capital, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(instance_id) DO UPDATE SET
                    status=excluded.status,
                    current_capital=excluded.current_capital,
                    allocated_capital=excluded.allocated_capital,
                    win_count=excluded.win_count,
                    loss_count=excluded.loss_count,
                    initial_capital=COALESCE(excluded.initial_capital, instance_state.initial_capital),
                    updated_at=excluded.updated_at
                """,
                (instance_id, status, current_capital, allocated_capital, win_count, loss_count, initial_capital, now)
            )
            await conn.commit()
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur sauvegarde état instance: {e}")
            return False

    async def recover_instance_state(self, instance_id: str) -> Optional[Dict[str, Any]]:
        try:
            conn = await self.get_conn()
            async with conn.execute("SELECT * FROM instance_state WHERE instance_id = ?", (instance_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.exception(f"❌ Erreur récupération état instance {instance_id}: {e}")
            return None


class StatePersistence:
    """
    Persistance d'état SQLite (Async) pour recovery après crash.
    """
    
    def __init__(self, db_path: str = "data/autobot_state.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        self.orders = OrderRepository(self.db_path, self._write_lock)
        self.audit = AuditRepository(self.db_path, self._write_lock)
        self.positions = PositionRepository(self.db_path, self._write_lock)
        self.instance_state = InstanceStateRepository(self.db_path, self._write_lock)
        self._initialized = False

    async def _ensure_columns(
        self,
        conn: aiosqlite.Connection,
        table: str,
        columns: Dict[str, str],
    ) -> None:
        async with conn.execute(f"PRAGMA table_info({table})") as cursor:
            existing = {row[1] for row in await cursor.fetchall()}
        for column, column_type in columns.items():
            if column not in existing:
                await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    async def _ensure_trade_ledger_trade_id_index(self, conn: aiosqlite.Connection) -> None:
        async with conn.execute(
            "SELECT trade_id, COUNT(*) AS count FROM trade_ledger "
            "GROUP BY trade_id HAVING COUNT(*) > 1 LIMIT 1"
        ) as cursor:
            duplicate = await cursor.fetchone()
        if duplicate is not None:
            logger.warning(
                "trade_ledger contains duplicate trade_id=%s; unique trade_id index deferred",
                duplicate[0],
            )
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_ledger_trade_id ON trade_ledger(trade_id)")
            return
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_ledger_trade_id_unique ON trade_ledger(trade_id)"
        )

    async def initialize(self):
        """Initialise la base de données (async)."""
        if self._initialized:
            return
        
        busy_timeout_ms = _env_int("SQLITE_BUSY_TIMEOUT_MS", 30_000, 1_000, 300_000)
        async with aiosqlite.connect(str(self.db_path), timeout=busy_timeout_ms / 1000.0) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
            
            # Create tables
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL,
                    symbol TEXT,
                    buy_price REAL NOT NULL,
                    volume REAL NOT NULL,
                    status TEXT DEFAULT 'open',
                    open_time TEXT NOT NULL,
                    strategy TEXT,
                    metadata TEXT
                )
            """)
            async with conn.execute("PRAGMA table_info(positions)") as cursor:
                position_columns = {row[1] for row in await cursor.fetchall()}
            if "symbol" not in position_columns:
                await conn.execute("ALTER TABLE positions ADD COLUMN symbol TEXT")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS instance_state (
                    instance_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    current_capital REAL NOT NULL,
                    allocated_capital REAL NOT NULL,
                    win_count INTEGER DEFAULT 0,
                    loss_count INTEGER DEFAULT 0,
                    initial_capital REAL,
                    updated_at TEXT NOT NULL
                )
            """)
            async with conn.execute("PRAGMA table_info(instance_state)") as cursor:
                instance_state_columns = {row[1] for row in await cursor.fetchall()}
            if "initial_capital" not in instance_state_columns:
                await conn.execute("ALTER TABLE instance_state ADD COLUMN initial_capital REAL")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS instance_lineage (
                    child_instance_id TEXT PRIMARY KEY,
                    parent_instance_id TEXT NOT NULL,
                    root_instance_id TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    child_capital REAL NOT NULL,
                    parent_capital_after REAL NOT NULL,
                    symbol TEXT,
                    strategy TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id TEXT NOT NULL,
                    instance_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume REAL NOT NULL,
                    profit REAL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (position_id) REFERENCES positions(id)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT NOT NULL,
                    position_id TEXT,
                    instance_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    expected_price REAL,
                    executed_price REAL NOT NULL,
                    volume REAL NOT NULL,
                    fees REAL DEFAULT 0,
                    slippage_bps REAL,
                    realized_pnl REAL,
                    is_opening_leg INTEGER DEFAULT 0,
                    is_closing_leg INTEGER DEFAULT 0,
                    exchange_order_id TEXT,
                    decision_id TEXT,
                    signal_id TEXT,
                    strategy_id TEXT,
                    timeframe TEXT,
                    signal_source TEXT,
                    gross_pnl REAL,
                    net_pnl REAL,
                    regime TEXT,
                    execution_liquidity TEXT,
                    execution_mode TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    client_order_id TEXT PRIMARY KEY,
                    exchange_order_id TEXT,
                    decision_id TEXT,
                    signal_id TEXT,
                    instance_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    requested_qty REAL NOT NULL,
                    filled_qty REAL NOT NULL DEFAULT 0,
                    avg_fill_price REAL,
                    status TEXT NOT NULL,
                    userref INTEGER,
                    retries INTEGER NOT NULL DEFAULT 0,
                    last_error_code TEXT,
                    last_error_message TEXT,
                    created_at TEXT NOT NULL,
                    sent_at TEXT,
                    ack_at TEXT,
                    terminal_at TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS order_state_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_order_id TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    source TEXT NOT NULL,
                    payload_hash TEXT,
                    occurred_at TEXT NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    decision_id TEXT,
                    signal_id TEXT,
                    client_order_id TEXT,
                    exchange_order_id TEXT,
                    instance_id TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    risk_snapshot TEXT NOT NULL,
                    balance_before TEXT,
                    balance_after TEXT,
                    fees REAL,
                    slippage_bps REAL,
                    order_from_status TEXT,
                    order_to_status TEXT,
                    exchange_raw_normalized TEXT,
                    prev_event_hash TEXT,
                    event_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS decision_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    decision_id TEXT,
                    signal_id TEXT,
                    instance_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    strategy TEXT,
                    engine TEXT,
                    event_type TEXT NOT NULL,
                    event_status TEXT,
                    reason TEXT,
                    source TEXT NOT NULL,
                    payload_json TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    outcome_id TEXT NOT NULL,
                    decision_ledger_id INTEGER NOT NULL,
                    decision_event_id TEXT,
                    decision_id TEXT,
                    signal_id TEXT,
                    instance_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    strategy TEXT,
                    engine TEXT,
                    side TEXT,
                    original_status TEXT,
                    rejection_reason TEXT,
                    reference_price REAL NOT NULL,
                    evaluation_price REAL NOT NULL,
                    gross_return_bps REAL NOT NULL,
                    estimated_cost_bps REAL NOT NULL,
                    net_return_bps REAL NOT NULL,
                    horizon_minutes INTEGER NOT NULL,
                    outcome_label TEXT NOT NULL,
                    source TEXT NOT NULL,
                    payload_json TEXT,
                    decision_created_at TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(decision_ledger_id, horizon_minutes)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS market_price_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sample_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    observed_at TEXT NOT NULL,
                    bucket_start TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(symbol, bucket_start)
                )
            """)
            
            # Indexes
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_instance ON trades(instance_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_lineage_parent ON instance_lineage(parent_instance_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_lineage_root ON instance_lineage(root_instance_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_ledger_symbol ON trade_ledger(symbol)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_ledger_created_at ON trade_ledger(created_at)")
            await self._ensure_columns(
                conn,
                "trade_ledger",
                {
                    "strategy_id": "TEXT",
                    "timeframe": "TEXT",
                    "signal_source": "TEXT",
                    "gross_pnl": "REAL",
                    "net_pnl": "REAL",
                    "regime": "TEXT",
                    "execution_mode": "TEXT",
                },
            )
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_ledger_strategy_id ON trade_ledger(strategy_id)")
            await self._ensure_trade_ledger_trade_id_index(conn)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_decision_ledger_symbol ON decision_ledger(symbol)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_decision_ledger_created_at ON decision_ledger(created_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_decision_ledger_instance_event ON decision_ledger(instance_id, event_type)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_signal_outcomes_symbol ON signal_outcomes(symbol)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_signal_outcomes_label ON signal_outcomes(outcome_label)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_signal_outcomes_evaluated_at ON signal_outcomes(evaluated_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_market_price_samples_symbol_time ON market_price_samples(symbol, observed_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_market_price_samples_created_at ON market_price_samples(created_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_transitions_client_order ON order_state_transitions(client_order_id)")
            
            await conn.commit()
        
        self._initialized = True
        logger.info(f"💾 Persistance Async initialisée: {self.db_path}")

    async def close(self):
        await self.orders.close()
        await self.audit.close()
        await self.positions.close()
        await self.instance_state.close()

    async def upsert_order(self, **kwargs) -> bool:
        await self.initialize()
        return await self.orders.upsert_order(**kwargs)

    async def transition_order_state(self, **kwargs) -> bool:
        await self.initialize()
        return await self.orders.transition_order_state(**kwargs)

    async def get_order(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        await self.initialize()
        return await self.orders.get_order(client_order_id)

    async def get_non_terminal_orders(self) -> List[Dict[str, Any]]:
        await self.initialize()
        return await self.orders.get_non_terminal_orders()

    async def append_audit_event(self, **kwargs) -> bool:
        await self.initialize()
        return await self.audit.append_audit_event(**kwargs)

    async def get_execution_fee(self, instance_id: str, exchange_order_id: str) -> Optional[float]:
        return await self.audit.get_execution_fee(instance_id, exchange_order_id)

    async def save_position(self, *args, **kwargs) -> bool:
        await self.initialize()
        if args:
            fields = (
                "position_id",
                "instance_id",
                "buy_price",
                "volume",
                "status",
                "strategy",
                "metadata",
            )
            if len(args) > len(fields):
                raise TypeError(f"save_position expected at most {len(fields)} positional arguments, got {len(args)}")
            for key, value in zip(fields, args):
                kwargs.setdefault(key, value)
        return await self.positions.save_position(**kwargs)

    async def update_position_status(self, position_id: str, status: str) -> bool:
        await self.initialize()
        return await self.positions.update_position_status(position_id, status)

    async def close_position_and_record_trade(self, position_id: str, trade_data: Dict[str, Any]) -> bool:
        await self.initialize()
        return await self.positions.close_position_and_record_trade(position_id, trade_data)

    async def recover_positions(self, instance_id: str, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        await self.initialize()
        return await self.positions.recover_positions(instance_id, symbol=symbol)

    async def save_instance_state(self, *args, **kwargs) -> bool:
        await self.initialize()
        return await self.instance_state.save_instance_state(*args, **kwargs)

    async def recover_instance_state(self, instance_id: str) -> Optional[Dict[str, Any]]:
        await self.initialize()
        return await self.instance_state.recover_instance_state(instance_id)

    async def cleanup_orphaned_instances(self, active_instance_ids: Optional[List[str]] = None) -> int:
        await self.initialize()
        if active_instance_ids is None:
            return 0
        if not active_instance_ids:
            return 0
        placeholders = ",".join("?" for _ in active_instance_ids)
        try:
            conn = await self.instance_state.get_conn()
            cursor = await conn.execute(
                f"DELETE FROM instance_state WHERE instance_id NOT IN ({placeholders})",
                tuple(active_instance_ids),
            )
            deleted = int(cursor.rowcount or 0)
            # Keep lineage as an immutable audit trail. It is also the durable
            # source enforcing one split per parent over the parent's lifetime.
            await conn.commit()
            return deleted
        except Exception as e:
            logger.exception(f"❌ Erreur cleanup_orphaned_instances: {e}")
            return 0

    async def record_instance_lineage(
        self,
        *,
        parent_instance_id: str,
        child_instance_id: str,
        root_instance_id: str,
        generation: int,
        child_capital: float,
        parent_capital_after: float,
        symbol: str = "",
        strategy: str = "",
        status: str = "active",
    ) -> bool:
        await self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = await self.instance_state.get_conn()
            await conn.execute(
                """
                INSERT INTO instance_lineage
                (child_instance_id, parent_instance_id, root_instance_id, generation,
                 child_capital, parent_capital_after, symbol, strategy, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(child_instance_id) DO UPDATE SET
                    parent_instance_id=excluded.parent_instance_id,
                    root_instance_id=excluded.root_instance_id,
                    generation=excluded.generation,
                    child_capital=excluded.child_capital,
                    parent_capital_after=excluded.parent_capital_after,
                    symbol=excluded.symbol,
                    strategy=excluded.strategy,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    child_instance_id,
                    parent_instance_id,
                    root_instance_id,
                    int(generation),
                    float(child_capital),
                    float(parent_capital_after),
                    symbol,
                    strategy,
                    status,
                    now,
                    now,
                ),
            )
            await conn.commit()
            return True
        except Exception as e:
            logger.exception(f"Erreur record_instance_lineage: {e}")
            return False

    async def get_instance_lineage(self) -> List[Dict[str, Any]]:
        await self.initialize()
        try:
            conn = await self.instance_state.get_conn()
            async with conn.execute(
                "SELECT * FROM instance_lineage ORDER BY generation ASC, created_at ASC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Erreur get_instance_lineage: {e}")
            return []

    async def get_parent_instance_split_count(self, parent_instance_id: str) -> Optional[int]:
        """Return durable lifetime split count, or None when it cannot be verified."""

        await self.initialize()
        try:
            conn = await self.instance_state.get_conn()
            async with conn.execute(
                "SELECT COUNT(*) FROM instance_lineage WHERE parent_instance_id = ?",
                (str(parent_instance_id),),
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0] if row else 0)
        except Exception as e:
            logger.exception(f"Erreur get_parent_instance_split_count: {e}")
            return None

    async def record_trade(self, position_id: str, instance_id: str,
                    side: str, price: float, volume: float,
                    profit: Optional[float] = None) -> bool:
        await self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = await self.instance_state.get_conn()
            await conn.execute(
                """
                INSERT INTO trades (position_id, instance_id, side, price, volume, profit, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (position_id, instance_id, side, price, volume, profit, now)
            )
            await conn.commit()
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur record_trade: {e}")
            return False

    async def append_trade_ledger(self, **kwargs) -> bool:
        await self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        try:
            strategy_id = kwargs.get("strategy_id")
            explicit_execution_mode = kwargs.get("execution_mode")
            execution_mode = normalize_execution_mode(explicit_execution_mode)
            block_reason = trade_ledger_append_block_reason(
                strategy_id,
                execution_mode=execution_mode,
                paper_capital_gate_attested=bool(kwargs.get("paper_capital_gate_attested", False)),
            )
            if block_reason is not None:
                logger.warning(
                    "Trade ledger append rejected: %s (symbol=%s mode=%s)",
                    block_reason,
                    kwargs.get("symbol"),
                    execution_mode,
                )
                return False
            cols = [
                "trade_id", "position_id", "instance_id", "symbol", "side", "expected_price", 
                "executed_price", "volume", "fees", "slippage_bps", "realized_pnl", 
                "is_opening_leg", "is_closing_leg", "exchange_order_id", "decision_id", 
                "signal_id", "strategy_id", "timeframe", "signal_source", "gross_pnl",
                "net_pnl", "regime", "execution_liquidity", "execution_mode", "created_at"
            ]
            vals = [
                kwargs.get("trade_id"), kwargs.get("position_id"), kwargs.get("instance_id"),
                kwargs.get("symbol"), kwargs.get("side"), kwargs.get("expected_price"),
                kwargs.get("executed_price"), kwargs.get("volume"), kwargs.get("fees", 0.0),
                kwargs.get("slippage_bps"), kwargs.get("realized_pnl"),
                int(kwargs.get("is_opening_leg", False)), int(kwargs.get("is_closing_leg", False)),
                kwargs.get("exchange_order_id"), kwargs.get("decision_id"), kwargs.get("signal_id"),
                strategy_id, kwargs.get("timeframe"), kwargs.get("signal_source"),
                kwargs.get("gross_pnl"), kwargs.get("net_pnl"), kwargs.get("regime"),
                kwargs.get("execution_liquidity"), execution_mode or EXECUTION_MODE_LEGACY_UNSPECIFIED, now
            ]
            query = f"INSERT OR IGNORE INTO trade_ledger ({', '.join(cols)}) VALUES ({', '.join(['?']*len(cols))})"

            async def _write() -> bool:
                conn = await self.orders.get_conn()
                cursor = await conn.execute(query, tuple(vals))
                await conn.commit()
                return int(cursor.rowcount or 0) > 0

            return await self.orders._with_write_retries("append_trade_ledger", _write)
        except Exception as e:
            logger.exception(f"❌ Erreur append_trade_ledger: {e}")
            return False

    async def append_decision_ledger_event(self, **kwargs) -> bool:
        await self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        try:
            payload = kwargs.get("payload_json")
            if payload is None:
                payload = kwargs.get("payload")
            if payload is not None and not isinstance(payload, str):
                payload = orjson.dumps(payload).decode("utf-8")
            cols = [
                "event_id",
                "decision_id",
                "signal_id",
                "instance_id",
                "symbol",
                "strategy",
                "engine",
                "event_type",
                "event_status",
                "reason",
                "source",
                "payload_json",
                "created_at",
            ]
            vals = [
                kwargs.get("event_id"),
                kwargs.get("decision_id"),
                kwargs.get("signal_id"),
                kwargs.get("instance_id"),
                kwargs.get("symbol"),
                kwargs.get("strategy"),
                kwargs.get("engine"),
                kwargs.get("event_type"),
                kwargs.get("event_status"),
                kwargs.get("reason"),
                kwargs.get("source", "runtime"),
                payload,
                kwargs.get("created_at") or now,
            ]
            query = (
                f"INSERT INTO decision_ledger ({', '.join(cols)}) "
                f"SELECT {', '.join(['?'] * len(cols))} "
                "WHERE NOT EXISTS (SELECT 1 FROM decision_ledger WHERE event_id = ?)"
            )

            async def _write() -> bool:
                conn = await self.orders.get_conn()
                cursor = await conn.execute(query, tuple([*vals, kwargs.get("event_id")]))
                await conn.commit()
                return int(cursor.rowcount or 0) > 0

            return await self.orders._with_write_retries("append_decision_ledger_event", _write)
        except Exception as e:
            logger.exception(f"Erreur append_decision_ledger_event: {e}")
            return False

    async def get_decision_ledger_events(
        self,
        *,
        limit: int = 50,
        symbol: Optional[str] = None,
        instance_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        clauses: List[str] = []
        args: List[Any] = []
        if symbol:
            clauses.append("symbol = ?")
            args.append(symbol)
        if instance_id:
            clauses.append("instance_id = ?")
            args.append(instance_id)
        if event_type:
            clauses.append("event_type = ?")
            args.append(event_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            "SELECT * FROM decision_ledger "
            f"{where} "
            "ORDER BY created_at DESC, id DESC "
            "LIMIT ?"
        )
        args.append(max(1, int(limit)))
        try:
            conn = await self.orders.get_conn()
            async with conn.execute(query, tuple(args)) as cursor:
                rows = await cursor.fetchall()
            results: List[Dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                payload_raw = item.get("payload_json")
                if isinstance(payload_raw, (str, bytes)):
                    try:
                        item["payload"] = orjson.loads(payload_raw)
                    except Exception:
                        item["payload"] = None
                else:
                    item["payload"] = None
                results.append(item)
            return results
        except Exception as e:
            logger.exception(f"Erreur get_decision_ledger_events: {e}")
            return []

    async def get_decision_outcome_candidates(
        self,
        *,
        horizon_minutes: int,
        limit: int = 200,
        oldest_created_at: Optional[str] = None,
        missing_source: str = "decision_learning_triple_barrier",
    ) -> List[Dict[str, Any]]:
        """Return mature decision events that still need a trusted outcome label."""
        await self.initialize()
        horizon = max(1, int(horizon_minutes))
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=horizon)
        clauses = [
            "dl.event_type = 'decision'",
            "dl.created_at <= ?",
            """
            NOT EXISTS (
                SELECT 1
                FROM signal_outcomes so
                WHERE so.decision_ledger_id = dl.id
                  AND so.horizon_minutes = ?
                  AND so.source = ?
            )
            """,
        ]
        args: List[Any] = [cutoff.isoformat(), horizon, str(missing_source)]
        if oldest_created_at:
            clauses.append("dl.created_at >= ?")
            args.append(str(oldest_created_at))
        query = """
            SELECT
                dl.*,
                (
                    SELECT sig.payload_json
                    FROM decision_ledger sig
                    WHERE sig.signal_id = dl.signal_id
                      AND sig.event_type = 'signal'
                    ORDER BY sig.created_at DESC, sig.id DESC
                    LIMIT 1
                ) AS linked_signal_payload_json
            FROM decision_ledger dl
            WHERE {where_clause}
            ORDER BY dl.created_at DESC, dl.id DESC
            LIMIT ?
        """.format(where_clause=" AND ".join(f"({clause.strip()})" for clause in clauses))
        args.append(max(1, int(limit)))
        try:
            conn = await self.orders.get_conn()
            async with conn.execute(query, tuple(args)) as cursor:
                rows = await cursor.fetchall()
            results: List[Dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                payload_raw = item.get("payload_json")
                if isinstance(payload_raw, (str, bytes)):
                    try:
                        item["payload"] = orjson.loads(payload_raw)
                    except Exception:
                        item["payload"] = None
                else:
                    item["payload"] = None
                linked_raw = item.get("linked_signal_payload_json")
                if isinstance(linked_raw, (str, bytes)):
                    try:
                        item["linked_signal_payload"] = orjson.loads(linked_raw)
                    except Exception:
                        item["linked_signal_payload"] = None
                else:
                    item["linked_signal_payload"] = None
                results.append(item)
            return results
        except Exception as e:
            logger.exception(f"Erreur get_decision_outcome_candidates: {e}")
            return []

    async def upsert_signal_outcome(self, **kwargs) -> bool:
        await self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = await self.orders.get_conn()
            payload = kwargs.get("payload_json")
            if payload is None:
                payload = kwargs.get("payload")
            if payload is not None and not isinstance(payload, str):
                payload = orjson.dumps(payload).decode("utf-8")
            cols = [
                "outcome_id",
                "decision_ledger_id",
                "decision_event_id",
                "decision_id",
                "signal_id",
                "instance_id",
                "symbol",
                "strategy",
                "engine",
                "side",
                "original_status",
                "rejection_reason",
                "reference_price",
                "evaluation_price",
                "gross_return_bps",
                "estimated_cost_bps",
                "net_return_bps",
                "horizon_minutes",
                "outcome_label",
                "source",
                "payload_json",
                "decision_created_at",
                "evaluated_at",
                "created_at",
            ]
            vals = [
                kwargs.get("outcome_id"),
                int(kwargs.get("decision_ledger_id")),
                kwargs.get("decision_event_id"),
                kwargs.get("decision_id"),
                kwargs.get("signal_id"),
                kwargs.get("instance_id"),
                kwargs.get("symbol"),
                kwargs.get("strategy"),
                kwargs.get("engine"),
                kwargs.get("side"),
                kwargs.get("original_status"),
                kwargs.get("rejection_reason"),
                float(kwargs.get("reference_price")),
                float(kwargs.get("evaluation_price")),
                float(kwargs.get("gross_return_bps")),
                float(kwargs.get("estimated_cost_bps")),
                float(kwargs.get("net_return_bps")),
                int(kwargs.get("horizon_minutes")),
                kwargs.get("outcome_label"),
                kwargs.get("source", "decision_learning"),
                payload,
                kwargs.get("decision_created_at"),
                kwargs.get("evaluated_at") or now,
                kwargs.get("created_at") or now,
            ]
            assignments = ", ".join(f"{col}=excluded.{col}" for col in cols if col not in {"outcome_id", "decision_ledger_id", "horizon_minutes", "created_at"})
            query = (
                f"INSERT INTO signal_outcomes ({', '.join(cols)}) "
                f"VALUES ({', '.join(['?'] * len(cols))}) "
                "ON CONFLICT(decision_ledger_id, horizon_minutes) DO UPDATE SET "
                f"{assignments}"
            )
            await conn.execute(query, tuple(vals))
            await conn.commit()
            return True
        except Exception as e:
            logger.exception(f"Erreur upsert_signal_outcome: {e}")
            return False

    async def get_signal_outcomes(
        self,
        *,
        limit: int = 50,
        symbol: Optional[str] = None,
        outcome_label: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        clauses: List[str] = []
        args: List[Any] = []
        if symbol:
            clauses.append("symbol = ?")
            args.append(symbol)
        if outcome_label:
            clauses.append("outcome_label = ?")
            args.append(outcome_label)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            "SELECT * FROM signal_outcomes "
            f"{where} "
            "ORDER BY evaluated_at DESC, id DESC "
            "LIMIT ?"
        )
        args.append(max(1, int(limit)))
        try:
            conn = await self.orders.get_conn()
            async with conn.execute(query, tuple(args)) as cursor:
                rows = await cursor.fetchall()
            results: List[Dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                payload_raw = item.get("payload_json")
                if isinstance(payload_raw, (str, bytes)):
                    try:
                        item["payload"] = orjson.loads(payload_raw)
                    except Exception:
                        item["payload"] = None
                else:
                    item["payload"] = None
                results.append(item)
            return results
        except Exception as e:
            logger.exception(f"Erreur get_signal_outcomes: {e}")
            return []

    async def append_market_price_samples(self, samples: List[Dict[str, Any]]) -> int:
        await self.initialize()
        if not samples:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        rows: List[tuple[Any, ...]] = []
        for sample in samples:
            try:
                symbol = str(sample.get("symbol") or "").upper()
                price = float(sample.get("price"))
                observed_at = str(sample.get("observed_at") or now)
                bucket_start = str(sample.get("bucket_start") or observed_at)
                source = str(sample.get("source") or "runtime_snapshot")
            except (TypeError, ValueError):
                continue
            if not symbol or price <= 0.0:
                continue
            rows.append((
                sample.get("sample_id") or f"px_{symbol}_{bucket_start}",
                symbol,
                price,
                observed_at,
                bucket_start,
                source,
                sample.get("created_at") or now,
            ))
        if not rows:
            return 0
        query = """
            INSERT INTO market_price_samples
            (sample_id, symbol, price, observed_at, bucket_start, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, bucket_start) DO UPDATE SET
                sample_id=excluded.sample_id,
                price=excluded.price,
                observed_at=excluded.observed_at,
                source=excluded.source,
                created_at=excluded.created_at
        """
        try:
            async def _write() -> int:
                conn = await self.orders.get_conn()
                await conn.executemany(query, rows)
                await conn.commit()
                return len(rows)

            return await self.orders._with_write_retries("append_market_price_samples", _write)
        except Exception as e:
            logger.exception(f"Erreur append_market_price_samples: {e}")
            return 0

    async def get_market_price_samples(
        self,
        *,
        symbols: List[str],
        start_at: str,
        end_at: str,
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        clean_symbols = [str(symbol).upper() for symbol in symbols if str(symbol or "").strip()]
        if not clean_symbols:
            return []
        placeholders = ",".join("?" for _ in clean_symbols)
        query = (
            "SELECT * FROM market_price_samples "
            f"WHERE symbol IN ({placeholders}) "
            "AND observed_at >= ? "
            "AND observed_at <= ? "
            "ORDER BY observed_at ASC, id ASC "
            "LIMIT ?"
        )
        args: List[Any] = [*clean_symbols, start_at, end_at, max(1, int(limit))]
        try:
            conn = await self.orders.get_conn()
            async with conn.execute(query, tuple(args)) as cursor:
                rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Erreur get_market_price_samples: {e}")
            return []

    async def purge_market_price_samples(self, *, older_than_hours: int) -> int:
        await self.initialize()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, int(older_than_hours)))
        try:
            async def _write() -> int:
                conn = await self.orders.get_conn()
                cursor = await conn.execute(
                    "DELETE FROM market_price_samples WHERE observed_at < ?",
                    (cutoff.isoformat(),),
                )
                deleted = int(cursor.rowcount or 0)
                await conn.commit()
                return deleted

            return await self.orders._with_write_retries("purge_market_price_samples", _write)
        except Exception as e:
            logger.exception(f"Erreur purge_market_price_samples: {e}")
            return 0

    async def get_trade_ledger_metrics(self, instance_id: Optional[str] = None) -> Dict[str, float]:
        await self.initialize()
        # Implementation similar to sync but with await
        where = ""
        args: tuple[Any, ...] = ()
        if instance_id:
            where = "WHERE instance_id = ?"
            args = (instance_id,)
        try:
            conn = await self.orders.get_conn()
            query = f"SELECT realized_pnl, fees FROM trade_ledger {where} AND is_closing_leg = 1" if where else \
                    "SELECT realized_pnl, fees FROM trade_ledger WHERE is_closing_leg = 1"
            async with conn.execute(query, args) as cursor:
                rows = await cursor.fetchall()
                pnls = [float(r["realized_pnl"]) for r in rows if r["realized_pnl"] is not None]
                total_fees = sum(float(r["fees"] or 0.0) for r in rows)

            gross_profit = sum(p for p in pnls if p > 0)
            gross_loss = abs(sum(p for p in pnls if p < 0))
            trade_count = len(pnls)
            wins = sum(1 for p in pnls if p > 0)
            losses = sum(1 for p in pnls if p < 0)
            avg_win = (gross_profit / wins) if wins else 0.0
            avg_loss = (gross_loss / losses) if losses else 0.0
            expectancy = (sum(pnls) / trade_count) if trade_count else 0.0
            pf = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
            return {
                "trade_count": float(trade_count), "gross_profit": float(gross_profit),
                "gross_loss": float(gross_loss), "profit_factor": float(pf),
                "expectancy": float(expectancy), "win_rate": float((wins / trade_count) if trade_count else 0.0),
                "avg_win": float(avg_win), "avg_loss": float(avg_loss),
                "total_fees": float(total_fees), "net_pnl": float(sum(pnls)),
            }
        except Exception as e:
            logger.exception(f"❌ Erreur get_trade_ledger_metrics: {e}")
            return {"trade_count": 0.0, "net_pnl": 0.0}

    async def get_trade_ledger_metrics_by_strategy(
        self,
        instance_id: Optional[str] = None,
        *,
        include_legacy: bool = False,
    ) -> Dict[str, Dict[str, float]]:
        """Return official closing-trade metrics by strategy.

        Legacy closing rows written before P0 may not have ``strategy_id``.
        They are historical evidence only: official strategy metrics exclude
        them by default so they cannot feed promotion or allocation gates.
        Pass ``include_legacy=True`` only for audit/reporting; those rows are
        then bucketed as ``legacy_unattributed``.
        """
        await self.initialize()
        clauses = ["is_closing_leg = 1"]
        args: list[Any] = []
        if instance_id:
            clauses.append("instance_id = ?")
            args.append(instance_id)
        where = f"WHERE {' AND '.join(clauses)}"
        try:
            conn = await self.orders.get_conn()
            async with conn.execute(
                f"""
                SELECT strategy_id, realized_pnl, net_pnl, fees
                FROM trade_ledger
                {where}
                """,
                tuple(args),
            ) as cursor:
                rows = await cursor.fetchall()

            buckets: Dict[str, list[float]] = {}
            fees_by_strategy: Dict[str, float] = {}
            for row in rows:
                raw_strategy_id = str(row["strategy_id"] or "").strip()
                if not raw_strategy_id:
                    if not include_legacy:
                        continue
                    strategy_id = LEGACY_UNATTRIBUTED_STRATEGY_ID
                else:
                    if official_paper_strategy_block_reason(raw_strategy_id) is not None:
                        continue
                    strategy_id = raw_strategy_id
                pnl_value = row["net_pnl"] if row["net_pnl"] is not None else row["realized_pnl"]
                if pnl_value is None:
                    continue
                buckets.setdefault(strategy_id, []).append(float(pnl_value))
                fees_by_strategy[strategy_id] = fees_by_strategy.get(strategy_id, 0.0) + float(row["fees"] or 0.0)

            result: Dict[str, Dict[str, float]] = {}
            for strategy_id, pnls in buckets.items():
                gross_profit = sum(p for p in pnls if p > 0)
                gross_loss = abs(sum(p for p in pnls if p < 0))
                trade_count = len(pnls)
                wins = sum(1 for p in pnls if p > 0)
                losses = sum(1 for p in pnls if p < 0)
                result[strategy_id] = {
                    "trade_count": float(trade_count),
                    "gross_profit": float(gross_profit),
                    "gross_loss": float(gross_loss),
                    "profit_factor": float(gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)),
                    "expectancy": float(sum(pnls) / trade_count if trade_count else 0.0),
                    "win_rate": float(wins / trade_count if trade_count else 0.0),
                    "loss_rate": float(losses / trade_count if trade_count else 0.0),
                    "total_fees": float(fees_by_strategy.get(strategy_id, 0.0)),
                    "net_pnl": float(sum(pnls)),
                }
            return result
        except Exception as e:
            logger.exception(f"❌ Erreur get_trade_ledger_metrics_by_strategy: {e}")
            return {}

    def get_pair_attribution_report(
        self,
        *,
        window_hours: Optional[int] = None,
        limit: Optional[int] = 20,
    ) -> Dict[str, Any]:
        """Return an offline, read-only attribution report by trading pair.

        Operator reports run outside the async execution loop.  They must not
        initialise repositories or mutate the runtime database merely to read
        a summary.  This small synchronous reader intentionally uses a
        read-only SQLite connection and ignores legacy/unattributed rows.
        """
        generated_at = datetime.now(timezone.utc)
        empty = {
            "generated_at": generated_at.isoformat(),
            "window_hours": int(window_hours) if window_hours is not None else None,
            "pair_count": 0,
            "totals": {
                "total_trades": 0,
                "total_realized_pnl": 0.0,
                "total_fees": 0.0,
                "net_pnl": 0.0,
            },
            "pairs": [],
        }
        if not self.db_path.exists():
            return empty

        clauses = [
            "is_closing_leg = 1",
            "strategy_id IS NOT NULL",
            "TRIM(strategy_id) != ''",
        ]
        params: List[Any] = []
        if window_hours is not None and int(window_hours) > 0:
            cutoff = generated_at - timedelta(hours=int(window_hours))
            clauses.append("created_at >= ?")
            params.append(cutoff.isoformat())
        where = " AND ".join(clauses)
        safe_limit = max(1, int(limit or 20))

        query = f"""
            SELECT
                symbol,
                COUNT(*) AS total_trades,
                SUM(CASE WHEN COALESCE(net_pnl, realized_pnl, 0.0) > 0 THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN COALESCE(net_pnl, realized_pnl, 0.0) < 0 THEN 1 ELSE 0 END) AS losses,
                SUM(COALESCE(realized_pnl, 0.0)) AS total_realized_pnl,
                SUM(COALESCE(net_pnl, realized_pnl, 0.0)) AS net_pnl,
                SUM(COALESCE(fees, 0.0)) AS total_fees,
                SUM(CASE WHEN COALESCE(net_pnl, realized_pnl, 0.0) > 0 THEN COALESCE(net_pnl, realized_pnl, 0.0) ELSE 0.0 END) AS gross_profit,
                SUM(CASE WHEN COALESCE(net_pnl, realized_pnl, 0.0) < 0 THEN -COALESCE(net_pnl, realized_pnl, 0.0) ELSE 0.0 END) AS gross_loss,
                SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS recent_trades_24h,
                MAX(created_at) AS last_trade_at
            FROM trade_ledger
            WHERE {where}
            GROUP BY symbol
            ORDER BY net_pnl DESC, symbol ASC
            LIMIT ?
        """
        recent_cutoff = (generated_at - timedelta(hours=24)).isoformat()
        try:
            uri = f"file:{self.db_path.resolve()}?mode=ro"
            with sqlite3.connect(uri, uri=True) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(query, [recent_cutoff, *params, safe_limit]).fetchall()
        except sqlite3.Error as exc:
            logger.warning("Pair attribution unavailable for %s: %s", self.db_path, exc)
            return empty

        pairs: List[Dict[str, Any]] = []
        for row in rows:
            total_trades = int(row["total_trades"] or 0)
            wins = int(row["wins"] or 0)
            losses = int(row["losses"] or 0)
            gross_profit = float(row["gross_profit"] or 0.0)
            gross_loss = float(row["gross_loss"] or 0.0)
            pairs.append({
                "symbol": str(row["symbol"]),
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "total_realized_pnl": float(row["total_realized_pnl"] or 0.0),
                "net_pnl": float(row["net_pnl"] or 0.0),
                "total_fees": float(row["total_fees"] or 0.0),
                "profit_factor": gross_profit / gross_loss if gross_loss > 0.0 else (999.0 if gross_profit > 0.0 else 0.0),
                "win_rate": wins / total_trades if total_trades else 0.0,
                "expectancy": float(row["net_pnl"] or 0.0) / total_trades if total_trades else 0.0,
                "recent_trades_24h": int(row["recent_trades_24h"] or 0),
                "last_trade_at": row["last_trade_at"],
            })

        empty["pair_count"] = len(pairs)
        empty["pairs"] = pairs
        empty["totals"] = {
            "total_trades": sum(pair["total_trades"] for pair in pairs),
            "total_realized_pnl": sum(pair["total_realized_pnl"] for pair in pairs),
            "total_fees": sum(pair["total_fees"] for pair in pairs),
            "net_pnl": sum(pair["net_pnl"] for pair in pairs),
        }
        return empty

    async def get_order_by_userref(self, userref: int) -> Optional[Dict[str, Any]]:
        await self.initialize()
        try:
            conn = await self.orders.get_conn()
            async with conn.execute("SELECT * FROM orders WHERE userref = ?", (userref,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.exception(f"❌ Erreur get_order_by_userref {userref}: {e}")
            return None

    async def cleanup_old_data(self, days: int = 30) -> int:
        await self.initialize()
        try:
            conn = await self.orders.get_conn()
            cursor = await conn.execute("DELETE FROM trades WHERE julianday('now') - julianday(timestamp) > ?", (days,))
            deleted = cursor.rowcount
            await conn.commit()
            return deleted
        except Exception as e:
            logger.exception(f"❌ Erreur nettoyage: {e}")
            return 0


# Singleton global
_persistence_instance: Optional[StatePersistence] = None

def get_persistence(db_path: str = "data/autobot_state.db") -> StatePersistence:
    global _persistence_instance
    if _persistence_instance is None:
        _persistence_instance = StatePersistence(db_path)
    return _persistence_instance


async def close_persistence() -> None:
    """Close and clear the process-wide persistence singleton safely.

    The singleton is intentionally process-scoped while AUTOBOT is running.
    Shutdown and preflight-only paths must release its aiosqlite worker threads
    before their event loop is closed. Calling this function repeatedly is
    safe and never creates a database connection.
    """

    global _persistence_instance
    persistence = _persistence_instance
    _persistence_instance = None
    if persistence is not None:
        await persistence.close()
