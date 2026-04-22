"""
Persistence - Sauvegarde et récupération d'état SQLite
Point #4: Crash recovery pour AUTOBOT V2
"""

import logging
import sqlite3
import threading as _threading
import orjson
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path
import threading

# ARCH-03: thread-local storage for SQLite connections (one conn per thread)
_local = _threading.local()

logger = logging.getLogger(__name__)


class _PersistenceRepositoryBase:
    """Shared helpers for SQLite repositories."""

    def __init__(self, get_conn, lock: threading.Lock):
        self._get_conn = get_conn
        self._lock = lock


class OrderRepository(_PersistenceRepositoryBase):
    """Order lifecycle persistence (orders + transitions)."""

    def upsert_order(
        self,
        client_order_id: str,
        instance_id: str,
        symbol: str,
        side: str,
        order_type: str,
        requested_qty: float,
        status: str = "NEW",
        decision_id: Optional[str] = None,
        signal_id: Optional[str] = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute(
                    """
                    INSERT INTO orders
                    (client_order_id, decision_id, signal_id, instance_id, symbol, side, order_type,
                     requested_qty, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(client_order_id) DO UPDATE SET
                        decision_id=excluded.decision_id,
                        signal_id=excluded.signal_id,
                        instance_id=excluded.instance_id,
                        symbol=excluded.symbol,
                        side=excluded.side,
                        order_type=excluded.order_type,
                        requested_qty=excluded.requested_qty,
                        updated_at=excluded.updated_at
                    """,
                    (
                        client_order_id, decision_id, signal_id, instance_id, symbol, side, order_type,
                        requested_qty, status, now, now,
                    ),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur upsert_order {client_order_id}: {e}")
            return False

    def transition_order_state(
        self,
        client_order_id: str,
        to_status: str,
        reason: str,
        source: str,
        exchange_order_id: Optional[str] = None,
        filled_qty: Optional[float] = None,
        avg_fill_price: Optional[float] = None,
        retries_delta: int = 0,
        last_error_code: Optional[str] = None,
        last_error_message: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        terminal = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}
        try:
            with self._lock:
                conn = self._get_conn()
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT status, retries, sent_at, ack_at FROM orders WHERE client_order_id = ?",
                    (client_order_id,),
                ).fetchone()
                if not row:
                    return False
                from_status = row["status"]
                payload_hash = hashlib.sha256(
                    orjson.dumps(payload or {}, option=orjson.OPT_SORT_KEYS)
                ).hexdigest()
                conn.execute(
                    """
                    INSERT INTO order_state_transitions
                    (client_order_id, from_status, to_status, reason, source, payload_hash, occurred_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (client_order_id, from_status, to_status, reason, source, payload_hash, now),
                )
                sent_at = row["sent_at"] or (now if to_status == "SENT" else None)
                ack_at = row["ack_at"] or (now if to_status == "ACK" else None)
                terminal_at = now if to_status in terminal else None
                conn.execute(
                    """
                    UPDATE orders SET
                        exchange_order_id = COALESCE(?, exchange_order_id),
                        filled_qty = COALESCE(?, filled_qty),
                        avg_fill_price = COALESCE(?, avg_fill_price),
                        status = ?,
                        retries = retries + ?,
                        last_error_code = COALESCE(?, last_error_code),
                        last_error_message = COALESCE(?, last_error_message),
                        sent_at = COALESCE(?, sent_at),
                        ack_at = COALESCE(?, ack_at),
                        terminal_at = COALESCE(?, terminal_at),
                        updated_at = ?
                    WHERE client_order_id = ?
                    """,
                    (
                        exchange_order_id, filled_qty, avg_fill_price, to_status, retries_delta,
                        last_error_code, last_error_message, sent_at, ack_at, terminal_at, now, client_order_id,
                    ),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur transition_order_state {client_order_id}: {e}")
            return False

    def get_order(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        try:
            with self._lock:
                conn = self._get_conn()
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM orders WHERE client_order_id = ?",
                    (client_order_id,),
                ).fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.exception(f"❌ Erreur get_order {client_order_id}: {e}")
            return None

    def get_non_terminal_orders(self) -> List[Dict[str, Any]]:
        try:
            with self._lock:
                conn = self._get_conn()
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM orders WHERE status IN ('NEW','SENT','ACK','PARTIAL')"
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.exception(f"❌ Erreur get_non_terminal_orders: {e}")
            return []


class AuditRepository(_PersistenceRepositoryBase):
    """Immutable audit trail persistence."""

    def append_audit_event(
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
            with self._lock:
                conn = self._get_conn()
                conn.row_factory = sqlite3.Row
                prev = conn.execute(
                    "SELECT event_hash FROM audit_events ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                prev_hash = prev["event_hash"] if prev else None
                normalized = {
                    "event_id": event_id,
                    "event_type": event_type,
                    "decision_id": decision_id,
                    "signal_id": signal_id,
                    "client_order_id": client_order_id,
                    "exchange_order_id": exchange_order_id,
                    "instance_id": instance_id,
                    "config_hash": config_hash,
                    "risk_snapshot": risk_snapshot,
                    "balance_before": balance_before,
                    "balance_after": balance_after,
                    "fees": fees,
                    "slippage_bps": slippage_bps,
                    "order_from_status": order_from_status,
                    "order_to_status": order_to_status,
                    "exchange_raw_normalized": exchange_raw_normalized,
                    "prev_event_hash": prev_hash,
                    "created_at": now,
                }
                event_hash = hashlib.sha256(
                    orjson.dumps(normalized, option=orjson.OPT_SORT_KEYS)
                ).hexdigest()
                conn.execute(
                    """
                    INSERT INTO audit_events
                    (event_id, event_type, decision_id, signal_id, client_order_id, exchange_order_id,
                     instance_id, config_hash, risk_snapshot, balance_before, balance_after, fees, slippage_bps,
                     order_from_status, order_to_status, exchange_raw_normalized, prev_event_hash, event_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id, event_type, decision_id, signal_id, client_order_id, exchange_order_id,
                        instance_id, config_hash,
                        orjson.dumps(risk_snapshot).decode("utf-8"),
                        orjson.dumps(balance_before).decode("utf-8") if balance_before is not None else None,
                        orjson.dumps(balance_after).decode("utf-8") if balance_after is not None else None,
                        fees, slippage_bps, order_from_status, order_to_status,
                        orjson.dumps(exchange_raw_normalized).decode("utf-8") if exchange_raw_normalized is not None else None,
                        prev_hash, event_hash, now,
                    ),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur append_audit_event {event_id}: {e}")
            return False

    def get_execution_fee(
        self,
        instance_id: str,
        exchange_order_id: str,
    ) -> Optional[float]:
        """Best-effort fee lookup from immutable audit trail for one exchange order id."""
        if not instance_id or not exchange_order_id:
            return None
        try:
            with self._lock:
                conn = self._get_conn()
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT fees
                    FROM audit_events
                    WHERE instance_id = ?
                      AND exchange_order_id = ?
                      AND fees IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (instance_id, exchange_order_id),
                ).fetchone()
            if row is None:
                return None
            fee = row["fees"]
            return float(fee) if fee is not None else None
        except Exception as e:
            logger.exception(f"❌ Erreur get_execution_fee {instance_id}/{exchange_order_id}: {e}")
            return None


class PositionRepository(_PersistenceRepositoryBase):
    """Open positions + trade history persistence."""

    def save_position(
        self,
        position_id: str,
        instance_id: str,
        buy_price: float,
        volume: float,
        status: str = "open",
        strategy: str = "",
        metadata: Optional[Dict] = None,
    ) -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute("""
                    INSERT OR REPLACE INTO positions
                    (id, instance_id, buy_price, volume, status, open_time, strategy, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    position_id, instance_id, buy_price, volume, status,
                    datetime.now(timezone.utc).isoformat(), strategy,
                    orjson.dumps(metadata).decode('utf-8') if metadata else None
                ))
                conn.commit()
            logger.debug(f"💾 Position sauvegardée: {instance_id}/{position_id}")
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur sauvegarde position: {e}")
            return False

    def update_position_status(self, position_id: str, status: str) -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute("UPDATE positions SET status = ? WHERE id = ?", (status, position_id))
                conn.commit()
                logger.debug(f"📝 Position mise à jour: {position_id} -> {status}")
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur mise à jour position: {e}")
            return False

    def close_position_and_record_trade(self, position_id: str, trade_data: Dict[str, Any]) -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                with conn:
                    conn.execute("DELETE FROM positions WHERE id = ?", (position_id,))
                    conn.execute("""
                        INSERT INTO trades
                        (position_id, instance_id, side, price, volume, profit, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        position_id,
                        trade_data['instance_id'],
                        trade_data['side'],
                        trade_data['price'],
                        trade_data['volume'],
                        trade_data.get('profit'),
                        trade_data['timestamp']
                    ))
                logger.debug(f"🗑️ Position {position_id} fermée + trade enregistré (atomique)")
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur fermeture position atomique: {e}")
            return False

    def recover_positions(self, instance_id: str) -> List[Dict[str, Any]]:
        try:
            with self._lock:
                conn = self._get_conn()
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM positions
                    WHERE instance_id = ? AND status = 'open'
                """, (instance_id,))
                positions = []
                for row in cursor.fetchall():
                    pos = dict(row)
                    if pos.get('metadata'):
                        pos['metadata'] = orjson.loads(pos['metadata'])
                    positions.append(pos)
            if positions:
                logger.warning(f"🔄 Recovery: {len(positions)} position(s) ouverte(s) trouvée(s) pour {instance_id}")
            else:
                logger.debug(f"✅ Pas de positions à récupérer pour {instance_id}")
            return positions
        except Exception as e:
            logger.exception(f"❌ Erreur récupération positions: {e}")
            return []


class InstanceStateRepository(_PersistenceRepositoryBase):
    """Instance lifecycle state persistence."""

    def save_instance_state(
        self,
        instance_id: str,
        status: str,
        current_capital: float,
        allocated_capital: float,
        win_count: int,
        loss_count: int,
    ) -> bool:
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute("""
                    INSERT OR REPLACE INTO instance_state
                    (instance_id, status, current_capital, allocated_capital,
                     win_count, loss_count, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    instance_id, status, current_capital, allocated_capital,
                    win_count, loss_count, datetime.now(timezone.utc).isoformat()
                ))
                conn.commit()
            logger.debug(f"💾 État instance sauvegardé: {instance_id}")
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur sauvegarde état instance: {e}")
            return False

    def recover_instance_state(self, instance_id: str) -> Optional[Dict[str, Any]]:
        try:
            with self._lock:
                conn = self._get_conn()
                conn.row_factory = sqlite3.Row
                row = conn.execute("""
                    SELECT * FROM instance_state
                    WHERE instance_id = ?
                """, (instance_id,)).fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.exception(f"❌ Erreur récupération état instance: {e}")
            return None


class StatePersistence:
    """
    Persistance d'état SQLite pour recovery après crash.
    
    Sauvegarde:
    - Positions ouvertes (pour récupération)
    - État des instances
    - Historique des trades
    """
    
    def __init__(self, db_path: str = "data/autobot_state.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.orders = OrderRepository(self._get_conn, self._lock)
        self.audit = AuditRepository(self._get_conn, self._lock)
        self.positions = PositionRepository(self._get_conn, self._lock)
        self.instance_state = InstanceStateRepository(self._get_conn, self._lock)
        
        # Initialise la base de données
        self._init_db()
        
        logger.info(f"💾 Persistance initialisée: {self.db_path}")
    
    def _get_conn(self) -> sqlite3.Connection:
        """Return a thread-local SQLite connection (avoids opening a new conn per call)."""
        conn = getattr(_local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=NORMAL")
            _local.conn = conn
        return conn

    def _init_db(self):
        """Crée les tables si elles n'existent pas"""
        with sqlite3.connect(self.db_path) as conn:
            # CORRECTION: Activer WAL mode pour meilleure concurrence
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")  # 5 secondes timeout
            # Positions ouvertes (pour recovery crash)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL,
                    buy_price REAL NOT NULL,
                    volume REAL NOT NULL,
                    status TEXT DEFAULT 'open',
                    open_time TEXT NOT NULL,
                    strategy TEXT,
                    metadata TEXT  -- JSON
                )
            """)
            
            # État des instances
            conn.execute("""
                CREATE TABLE IF NOT EXISTS instance_state (
                    instance_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    current_capital REAL NOT NULL,
                    allocated_capital REAL NOT NULL,
                    win_count INTEGER DEFAULT 0,
                    loss_count INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Historique des trades
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id TEXT NOT NULL,
                    instance_id TEXT NOT NULL,
                    side TEXT NOT NULL,  -- 'buy', 'sell'
                    price REAL NOT NULL,
                    volume REAL NOT NULL,
                    profit REAL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (position_id) REFERENCES positions(id)
                )
            """)

            # Canonical immutable trade ledger (decision/execution attribution)
            conn.execute("""
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
                    execution_liquidity TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            # Backward-compatible migration for pre-existing DBs.
            try:
                conn.execute("ALTER TABLE trade_ledger ADD COLUMN execution_liquidity TEXT")
            except sqlite3.OperationalError:
                pass

            # Persisted order lifecycle state machine
            conn.execute("""
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

            conn.execute("""
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

            # Immutable audit log (append-only by trigger)
            conn.execute("""
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

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS audit_events_no_update
                BEFORE UPDATE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit_events is immutable');
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
                BEFORE DELETE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit_events is immutable');
                END;
            """)

            # Keep trade_ledger append-only as well
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trade_ledger_no_update
                BEFORE UPDATE ON trade_ledger
                BEGIN
                    SELECT RAISE(ABORT, 'trade_ledger is immutable');
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trade_ledger_no_delete
                BEFORE DELETE ON trade_ledger
                BEGIN
                    SELECT RAISE(ABORT, 'trade_ledger is immutable');
                END;
            """)
            
            # CORRECTION: Index pour performances
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_instance ON trades(instance_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_ledger_symbol ON trade_ledger(symbol)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_ledger_created_at ON trade_ledger(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_transitions_client_order ON order_state_transitions(client_order_id)")
            
            conn.commit()
            logger.debug("📁 Tables SQLite initialisées")

    def upsert_order(
        self,
        client_order_id: str,
        instance_id: str,
        symbol: str,
        side: str,
        order_type: str,
        requested_qty: float,
        status: str = "NEW",
        decision_id: Optional[str] = None,
        signal_id: Optional[str] = None,
    ) -> bool:
        """Create or update an order lifecycle record."""
        return self.orders.upsert_order(
            client_order_id=client_order_id,
            instance_id=instance_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            requested_qty=requested_qty,
            status=status,
            decision_id=decision_id,
            signal_id=signal_id,
        )

    def transition_order_state(
        self,
        client_order_id: str,
        to_status: str,
        reason: str,
        source: str,
        exchange_order_id: Optional[str] = None,
        filled_qty: Optional[float] = None,
        avg_fill_price: Optional[float] = None,
        retries_delta: int = 0,
        last_error_code: Optional[str] = None,
        last_error_message: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Persist a state transition for the order state machine."""
        return self.orders.transition_order_state(
            client_order_id=client_order_id,
            to_status=to_status,
            reason=reason,
            source=source,
            exchange_order_id=exchange_order_id,
            filled_qty=filled_qty,
            avg_fill_price=avg_fill_price,
            retries_delta=retries_delta,
            last_error_code=last_error_code,
            last_error_message=last_error_message,
            payload=payload,
        )

    def get_order(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        return self.orders.get_order(client_order_id)

    def get_non_terminal_orders(self) -> List[Dict[str, Any]]:
        """Used for crash recovery/replay."""
        return self.orders.get_non_terminal_orders()

    def append_audit_event(
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
        """Append immutable audit event with hash-chain."""
        return self.audit.append_audit_event(
            event_id=event_id,
            event_type=event_type,
            instance_id=instance_id,
            config_hash=config_hash,
            risk_snapshot=risk_snapshot,
            decision_id=decision_id,
            signal_id=signal_id,
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
            balance_before=balance_before,
            balance_after=balance_after,
            fees=fees,
            slippage_bps=slippage_bps,
            order_from_status=order_from_status,
            order_to_status=order_to_status,
            exchange_raw_normalized=exchange_raw_normalized,
        )

    def get_execution_fee(
        self,
        instance_id: str,
        exchange_order_id: Optional[str],
    ) -> Optional[float]:
        """Resolve a persisted execution fee (audit first, then trade ledger fallback)."""
        if not instance_id or not exchange_order_id:
            return None
        fee = self.audit.get_execution_fee(instance_id, exchange_order_id)
        if fee is not None:
            return fee
        try:
            with self._lock:
                conn = self._get_conn()
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT fees
                    FROM trade_ledger
                    WHERE instance_id = ?
                      AND exchange_order_id = ?
                      AND fees IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (instance_id, exchange_order_id),
                ).fetchone()
            if row is None:
                return None
            raw = row["fees"]
            return float(raw) if raw is not None else None
        except Exception as e:
            logger.exception(f"❌ Erreur get_execution_fee ledger fallback {instance_id}/{exchange_order_id}: {e}")
            return None
    
    def save_position(self, position_id: str, instance_id: str, 
                      buy_price: float, volume: float,
                      status: str = "open", strategy: str = "",
                      metadata: Optional[Dict] = None) -> bool:
        """
        Sauvegarde une position ouverte.
        Appelé quand une position est créée.
        """
        return self.positions.save_position(
            position_id=position_id,
            instance_id=instance_id,
            buy_price=buy_price,
            volume=volume,
            status=status,
            strategy=strategy,
            metadata=metadata,
        )
    
    def update_position_status(self, position_id: str, status: str) -> bool:
        """
        Met à jour le statut d'une position.
        """
        return self.positions.update_position_status(position_id, status)

    def close_position_and_record_trade(self, position_id: str, 
                                        trade_data: Dict[str, Any]) -> bool:
        """
        CORRECTION: Opération atomique - ferme position ET enregistre le trade
        dans une seule transaction. Évite les "ghost positions".
        """
        return self.positions.close_position_and_record_trade(position_id, trade_data)
    
    def save_instance_state(self, instance_id: str, status: str,
                           current_capital: float, allocated_capital: float,
                           win_count: int, loss_count: int) -> bool:
        """
        Sauvegarde l'état d'une instance.
        Appelé périodiquement et à l'arrêt.
        """
        return self.instance_state.save_instance_state(
            instance_id=instance_id,
            status=status,
            current_capital=current_capital,
            allocated_capital=allocated_capital,
            win_count=win_count,
            loss_count=loss_count,
        )
    
    def record_trade(self, position_id: str, instance_id: str,
                    side: str, price: float, volume: float,
                    profit: Optional[float] = None) -> bool:
        """
        Enregistre un trade dans l'historique.
        """
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute("""
                    INSERT INTO trades
                    (position_id, instance_id, side, price, volume, profit, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    position_id, instance_id, side, price, volume, profit,
                    datetime.now(timezone.utc).isoformat()
                ))
                conn.commit()

            logger.debug(f"💾 Trade enregistré: {instance_id} {side} {volume}")
            return True
            
        except Exception as e:
            logger.exception(f"❌ Erreur enregistrement trade: {e}")
            return False

    def append_trade_ledger(
        self,
        trade_id: str,
        instance_id: str,
        symbol: str,
        side: str,
        executed_price: float,
        volume: float,
        fees: float = 0.0,
        expected_price: Optional[float] = None,
        slippage_bps: Optional[float] = None,
        realized_pnl: Optional[float] = None,
        position_id: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        execution_liquidity: Optional[str] = None,
        is_opening_leg: bool = False,
        is_closing_leg: bool = False,
    ) -> bool:
        """Append one immutable trade leg to canonical ledger."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute(
                    """
                    INSERT INTO trade_ledger
                    (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
                     volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
                     exchange_order_id, decision_id, signal_id, execution_liquidity, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trade_id,
                        position_id,
                        instance_id,
                        symbol,
                        side,
                        expected_price,
                        executed_price,
                        volume,
                        fees,
                        slippage_bps,
                        realized_pnl,
                        int(is_opening_leg),
                        int(is_closing_leg),
                        exchange_order_id,
                        decision_id,
                        signal_id,
                        execution_liquidity,
                        now,
                    ),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.exception(f"❌ Erreur append_trade_ledger {trade_id}: {e}")
            return False

    def get_trade_ledger_metrics(self, instance_id: Optional[str] = None) -> Dict[str, float]:
        """
        Compute persisted PF/expectancy metrics from trade_ledger sell legs.
        PF uses gross winning pnl / gross losing pnl (abs).
        """
        where = ""
        args: tuple[Any, ...] = ()
        if instance_id:
            where = "WHERE instance_id = ?"
            args = (instance_id,)
        try:
            with self._lock:
                conn = self._get_conn()
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    f"""
                    SELECT realized_pnl, fees
                    FROM trade_ledger
                    {where}
                    AND is_closing_leg = 1
                    """ if where else """
                    SELECT realized_pnl, fees
                    FROM trade_ledger
                    WHERE is_closing_leg = 1
                    """,
                    args,
                ).fetchall()
            pnls: List[float] = []
            total_fees = 0.0
            for row in rows:
                pnl = row["realized_pnl"]
                if pnl is None:
                    continue
                pnls.append(float(pnl))
                total_fees += float(row["fees"] or 0.0)

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
                "trade_count": float(trade_count),
                "gross_profit": float(gross_profit),
                "gross_loss": float(gross_loss),
                "profit_factor": float(pf),
                "expectancy": float(expectancy),
                "win_rate": float((wins / trade_count) if trade_count else 0.0),
                "avg_win": float(avg_win),
                "avg_loss": float(avg_loss),
                "total_fees": float(total_fees),
                "net_pnl": float(sum(pnls)),
            }
        except Exception as e:
            logger.exception(f"❌ Erreur get_trade_ledger_metrics: {e}")
            return {
                "trade_count": 0.0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "profit_factor": 0.0,
                "expectancy": 0.0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "total_fees": 0.0,
                "net_pnl": 0.0,
            }

    def get_pair_attribution_report(
        self,
        *,
        window_hours: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Compute pair-level realized attribution from immutable trade_ledger.

        Uses closing legs with non-null realized_pnl.
        """
        now = datetime.now(timezone.utc)
        cutoff_iso = None
        if window_hours is not None and int(window_hours) > 0:
            cutoff_iso = (now - timedelta(hours=int(window_hours))).isoformat()

        try:
            with self._lock:
                conn = self._get_conn()
                conn.row_factory = sqlite3.Row
                if cutoff_iso:
                    rows = conn.execute(
                        """
                        SELECT symbol, realized_pnl, fees, created_at
                        FROM trade_ledger
                        WHERE is_closing_leg = 1
                          AND realized_pnl IS NOT NULL
                          AND created_at >= ?
                        ORDER BY created_at DESC
                        """,
                        (cutoff_iso,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT symbol, realized_pnl, fees, created_at
                        FROM trade_ledger
                        WHERE is_closing_leg = 1
                          AND realized_pnl IS NOT NULL
                        ORDER BY created_at DESC
                        """
                    ).fetchall()

                last24_cutoff = (now - timedelta(hours=24)).isoformat()
                recent_rows = conn.execute(
                    """
                    SELECT symbol, COUNT(*) AS c
                    FROM trade_ledger
                    WHERE is_closing_leg = 1
                      AND realized_pnl IS NOT NULL
                      AND created_at >= ?
                    GROUP BY symbol
                    """,
                    (last24_cutoff,),
                ).fetchall()

            recent_24h_by_symbol = {str(r["symbol"]): int(r["c"]) for r in recent_rows}
            agg: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                symbol = str(row["symbol"] or "UNKNOWN")
                pnl = float(row["realized_pnl"] or 0.0)
                fees = float(row["fees"] or 0.0)
                created_at = str(row["created_at"])
                item = agg.setdefault(
                    symbol,
                    {
                        "symbol": symbol,
                        "total_trades": 0,
                        "wins": 0,
                        "losses": 0,
                        "total_realized_pnl": 0.0,
                        "total_fees": 0.0,
                        "gross_profit": 0.0,
                        "gross_loss": 0.0,
                        "last_trade_at": None,
                        "recent_trades_24h": int(recent_24h_by_symbol.get(symbol, 0)),
                    },
                )
                item["total_trades"] += 1
                item["total_realized_pnl"] += pnl
                item["total_fees"] += fees
                if pnl > 0:
                    item["wins"] += 1
                    item["gross_profit"] += pnl
                elif pnl < 0:
                    item["losses"] += 1
                    item["gross_loss"] += abs(pnl)
                if item["last_trade_at"] is None or created_at > str(item["last_trade_at"]):
                    item["last_trade_at"] = created_at

            pairs: List[Dict[str, Any]] = []
            for symbol, item in agg.items():
                total = int(item["total_trades"])
                wins = int(item["wins"])
                losses = int(item["losses"])
                gp = float(item["gross_profit"])
                gl = float(item["gross_loss"])
                pf = (gp / gl) if gl > 0 else (999.0 if gp > 0 else 0.0)
                win_rate = (wins / total) if total else 0.0
                expectancy = (float(item["total_realized_pnl"]) / total) if total else 0.0
                pairs.append(
                    {
                        "symbol": symbol,
                        "total_trades": total,
                        "wins": wins,
                        "losses": losses,
                        "total_realized_pnl": float(item["total_realized_pnl"]),
                        "total_fees": float(item["total_fees"]),
                        "profit_factor": float(pf),
                        "win_rate": float(win_rate),
                        "expectancy": float(expectancy),
                        "recent_trades_24h": int(item["recent_trades_24h"]),
                        "last_trade_at": item["last_trade_at"],
                    }
                )

            pairs.sort(key=lambda p: (p["total_realized_pnl"], p["profit_factor"]), reverse=True)
            if limit is not None and int(limit) > 0:
                pairs = pairs[: int(limit)]

            total_trades = sum(int(p["total_trades"]) for p in pairs)
            total_pnl = sum(float(p["total_realized_pnl"]) for p in pairs)
            total_fees = sum(float(p["total_fees"]) for p in pairs)

            return {
                "generated_at": now.isoformat(),
                "window_hours": int(window_hours) if window_hours is not None else None,
                "pair_count": len(pairs),
                "totals": {
                    "total_trades": int(total_trades),
                    "total_realized_pnl": float(total_pnl),
                    "total_fees": float(total_fees),
                },
                "pairs": pairs,
            }
        except Exception as e:
            logger.exception(f"❌ Erreur get_pair_attribution_report: {e}")
            return {
                "generated_at": now.isoformat(),
                "window_hours": int(window_hours) if window_hours is not None else None,
                "pair_count": 0,
                "totals": {
                    "total_trades": 0,
                    "total_realized_pnl": 0.0,
                    "total_fees": 0.0,
                },
                "pairs": [],
            }
    
    def recover_positions(self, instance_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les positions ouvertes après un crash.
        Appelé au démarrage d'une instance.
        """
        return self.positions.recover_positions(instance_id)
    
    def recover_instance_state(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère l'état sauvegardé d'une instance.
        """
        return self.instance_state.recover_instance_state(instance_id)
    
    def cleanup_old_data(self, days: int = 30) -> int:
        """
        Nettoie les vieilles données (trades fermés, etc.).
        Retourne le nombre de lignes supprimées.
        """
        try:
            cutoff = datetime.now(timezone.utc).timestamp() - (days * 24 * 3600)
            
            with self._lock:
                conn = self._get_conn()
                cursor = conn.execute("""
                    DELETE FROM trades
                    WHERE julianday('now') - julianday(timestamp) > ?
                """, (days,))
                deleted = cursor.rowcount
                conn.commit()
                    
            if deleted > 0:
                logger.info(f"🧹 Nettoyage: {deleted} vieux trades supprimés")
            return deleted
            
        except Exception as e:
            logger.exception(f"❌ Erreur nettoyage: {e}")
            return 0



    def cleanup_orphaned_instances(self, max_age_hours: int = 24) -> int:
        """
        Nettoie les enregistrements instance_state orphelins.
        Supprime les instances arrêtées depuis plus de max_age_hours.
        Retourne le nombre de lignes supprimées.
        """
        try:
            with self._lock:
                conn = self._get_conn()
                cursor = conn.execute("""
                    DELETE FROM instance_state 
                    WHERE status='stopped' 
                    AND updated_at < datetime('now', '-1 day')
                """)
                deleted = cursor.rowcount
                conn.commit()
            
            if deleted > 0:
                logger.info(f"🧹 Nettoyage: {deleted} instances orphelines supprimées")
            return deleted
        except Exception as e:
            logger.exception(f"❌ Erreur nettoyage instances orphelines: {e}")
            return 0

# Singleton global - CORRECTION Phase 4: Thread-safe
_persistence_instance: Optional[StatePersistence] = None
_persistence_lock = threading.Lock()


def get_persistence(db_path: str = "data/autobot_state.db") -> StatePersistence:
    """
    Retourne l'instance singleton de persistance (thread-safe).

    CORRECTION Phase 4: Utilise un lock pour éviter race condition
    si deux threads appellent get_persistence() simultanément.
    """
    global _persistence_instance

    with _persistence_lock:
        if _persistence_instance is None:
            _persistence_instance = StatePersistence(db_path)
        return _persistence_instance


def reset_persistence():
    """Reset le singleton (pour tests)"""
    global _persistence_instance
    _persistence_instance = None


# OPTIMISATION: Backup et maintenance automatique
def backup_database(source: str = "data/autobot_state.db", 
                    backup_dir: str = "data/backups") -> str:
    """
    CORRECTION: Crée un backup atomique de la base SQLite avec timestamp.
    Utilise l'API SQLite backup pour garantir la cohérence même pendant les écritures.
    
    Returns:
        Chemin du fichier backup créé
    """
    from pathlib import Path
    
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = Path(backup_dir) / f"autobot_state_{timestamp}.db"
    
    # CORRECTION: Backup atomique via API SQLite
    # Évite la corruption si une écriture est en cours pendant le backup
    try:
        with sqlite3.connect(source) as source_conn:
            with sqlite3.connect(str(backup_path)) as backup_conn:
                source_conn.backup(backup_conn)
        logger.info(f"💾 Backup atomique créé: {backup_path}")
    except AttributeError:
        # Fallback pour Python < 3.7 (backup() ajouté en 3.7)
        import shutil
        shutil.copy2(source, backup_path)
        logger.info(f"💾 Backup créé (fallback copy): {backup_path}")
    
    return str(backup_path)


def cleanup_old_backups(backup_dir: str = "data/backups", keep_days: int = 7) -> int:
    """
    Supprime les backups vieux de plus de N jours
    
    Returns:
        Nombre de backups supprimés
    """
    from pathlib import Path
    import shutil
    
    backup_path = Path(backup_dir)
    if not backup_path.exists():
        return 0
    
    cutoff = datetime.now(timezone.utc).timestamp() - (keep_days * 24 * 3600)
    deleted = 0
    
    for backup_file in backup_path.glob("autobot_state_*.db"):
        if backup_file.stat().st_mtime < cutoff:
            backup_file.unlink()
            deleted += 1
            
    if deleted > 0:
        logger.info(f"🧹 {deleted} vieux backups supprimés")
    
    return deleted


class MaintenanceScheduler:
    """
    Planificateur de maintenance automatique
    - Backup quotidien
    - Nettoyage des vieilles données
    """
    
    def __init__(self, persistence: StatePersistence,
                 backup_interval_hours: int = 1,  # PROD-04: hourly backups
                 cleanup_interval_hours: int = 24):
        self.persistence = persistence
        self.backup_interval = backup_interval_hours * 3600
        self.cleanup_interval = cleanup_interval_hours * 3600
        self._last_backup = 0
        self._last_cleanup = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
    def start(self):
        """Démarre le planificateur"""
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("🔄 Maintenance scheduler démarré")
        
    def stop(self):
        """Arrête le planificateur"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            
    def _loop(self):
        """Boucle de maintenance"""
        import time
        
        while self._running:
            now = time.time()
            
            # Backup quotidien
            if now - self._last_backup >= self.backup_interval:
                try:
                    backup_database()
                    cleanup_old_backups()
                    self._last_backup = now
                except Exception as e:
                    logger.exception(f"❌ Erreur backup: {e}")
            
            # Nettoyage quotidien
            if now - self._last_cleanup >= self.cleanup_interval:
                try:
                    deleted = self.persistence.cleanup_old_data(days=30)
                    logger.info(f"🧹 Maintenance: {deleted} vieux trades nettoyés")
                    self._last_cleanup = now
                except Exception as e:
                    logger.exception(f"❌ Erreur nettoyage: {e}")
            
            time.sleep(60)  # Check toutes les minutes


# Singleton pour la maintenance
_maintenance_scheduler: Optional[MaintenanceScheduler] = None


def start_maintenance(persistence: StatePersistence):
    """Démarre le planificateur de maintenance global"""
    global _maintenance_scheduler
    if _maintenance_scheduler is None:
        _maintenance_scheduler = MaintenanceScheduler(persistence)
        _maintenance_scheduler.start()
