"""
Trading Instance — Full Async
MIGRATION P0: Replaces instance.py (threading)

Uses:
- asyncio.Lock instead of threading.Lock
- async def on_price_update() instead of sync callback
- run_in_executor for SQLite persistence (sync I/O)
- All public methods are async

P3 extension: Queue-based consumption
- attach_queue(queue): register an InstanceQueue (from AsyncDispatcher)
- start_queue_consumer(): start dedicated consumer task
- _queue_consumer_loop(): async loop that consumes from the queue
- stop(): drains the queue before stopping (graceful shutdown)

P4 extension: Hot/Cold path separation
- on_price_update() is the hot path: no lock, no I/O, no allocation
- check_leverage_downgrade() moved to cold path (periodic, via ColdPathScheduler)
- HotPathOptimizer injected via attach_hot_optimizer() for latency telemetry

Public API identical to TradingInstance (with async/await).
"""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from collections import deque
from datetime import datetime, timezone, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from .websocket_client import TickerData
from .persistence import get_persistence
from .instance import (
    InstanceStatus,
    LeverageLevel,
    Position,
    Trade,
)

logger = logging.getLogger(__name__)


class TradingInstanceAsync:
    """
    Async trading instance managed by OrchestratorAsync.

    Drop-in async replacement for TradingInstance.
    """

    # Kraken symbol mapping (reused from instance.py)
    _KRAKEN_SYMBOL_MAP = {
        "BTC/EUR": "XXBTZEUR",
        "BTC/USD": "XXBTZUSD",
        "ETH/EUR": "XETHZEUR",
        "ETH/USD": "XETHZUSD",
        "XRP/EUR": "XXRPZEUR",
        "XRP/USD": "XXRPZUSD",
        "SOL/EUR": "SOLEUR",
        "SOL/USD": "SOLUSD",
        "ADA/EUR": "ADAEUR",
        "ADA/USD": "ADAUSD",
        "DOT/EUR": "DOTEUR",
        "DOT/USD": "DOTUSD",
    }

    def __init__(
        self,
        instance_id: str,
        config: Any,
        orchestrator: Any,
        order_executor: Optional[Any] = None,
    ) -> None:
        self.id = instance_id
        self.config = config
        self.orchestrator = orchestrator
        self._order_executor = order_executor

        # State
        self.status = InstanceStatus.INITIALIZING
        self._lock = asyncio.Lock()

        # Capital
        self._initial_capital: float = config.initial_capital
        self._current_capital: float = config.initial_capital
        self._allocated_capital: float = 0.0

        # Positions & trades
        self._positions: Dict[str, Position] = {}
        self._max_trades_history = 1000
        self._trades: deque = deque(maxlen=self._max_trades_history)
        self._open_orders: Dict[str, Any] = {}

        # Performance
        self._win_count: int = 0
        self._loss_count: int = 0
        self._win_streak: int = 0
        self._max_drawdown: float = 0.0
        self._peak_capital: float = config.initial_capital

        # Price
        self._last_price: Optional[float] = None
        self._max_history_size = 1000
        self._price_history: deque = deque(maxlen=self._max_history_size)

        # Strategy (set by _init_strategy)
        self._strategy: Any = None
        self._signal_handler: Any = None

        # Callbacks
        self._on_trade: Optional[Callable] = None
        self._on_position_open: Optional[Callable] = None
        self._on_position_close: Optional[Callable] = None

        # Persistence (sync — wrapped via run_in_executor)
        self._persistence = get_persistence()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Fee optimizer
        self._fee_optimizer = None
        try:
            from .modules.fee_optimizer import FeeOptimizer
            self._fee_optimizer = FeeOptimizer()
        except Exception:
            pass

        # Leverage
        self._leverage_level = LeverageLevel.X1

        # P3: Queue-based dispatch (optional — backward-compatible)
        # Set via attach_queue() before start()
        self._instance_queue: Optional[Any] = None      # InstanceQueue | None
        self._queue_consumer_task: Optional[asyncio.Task] = None

        # P4: Hot-path optimizer — injected by orchestrator via attach_hot_optimizer()
        # None → latency measurement skipped (backward-compatible).
        self._hot_optimizer: Optional[Any] = None       # HotPathOptimizer | None

        logger.info(f"📊 InstanceAsync {self.id} initialisée: {config.name}")

    # ------------------------------------------------------------------
    # Persistence helpers (sync I/O → run_in_executor)
    # ------------------------------------------------------------------

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return self._loop

    async def _run_sync(self, fn: Callable, *args: Any) -> Any:
        """Run a sync function in executor (thread pool) to avoid blocking."""
        loop = self._get_loop()
        return await loop.run_in_executor(None, fn, *args)

    # ------------------------------------------------------------------
    # Recovery & save
    # ------------------------------------------------------------------

    async def recover_state(self) -> None:
        """Recover state from SQLite (called at startup)."""
        try:
            saved_positions = await self._run_sync(
                self._persistence.recover_positions, self.id
            )
            if saved_positions:
                logger.warning(
                    f"🔄 Recovery {self.id}: {len(saved_positions)} position(s)"
                )
                async with self._lock:
                    for pos_data in saved_positions:
                        metadata = pos_data.get("metadata") or {}
                        position = Position(
                            id=pos_data["id"],
                            buy_price=pos_data["buy_price"],
                            volume=pos_data["volume"],
                            status="open",
                            open_time=datetime.fromisoformat(pos_data["open_time"]),
                            stop_loss=metadata.get("stop_loss"),
                            take_profit=metadata.get("take_profit"),
                        )
                        self._positions[position.id] = position
                        self._allocated_capital += position.buy_price * position.volume

            saved_state = await self._run_sync(
                self._persistence.recover_instance_state, self.id
            )
            if saved_state:
                async with self._lock:
                    self._current_capital = saved_state["current_capital"]
                    self._win_count = saved_state.get("win_count", 0)
                    self._loss_count = saved_state.get("loss_count", 0)
        except Exception as exc:
            logger.exception(f"❌ Erreur recovery état {self.id}: {exc}")

    async def save_state(self) -> bool:
        """Save instance state to SQLite."""
        try:
            async with self._lock:
                cc = self._current_capital
                ac = self._allocated_capital
                wc = self._win_count
                lc = self._loss_count
                st = self.status.value

            await self._run_sync(
                self._persistence.save_instance_state,
                self.id,
                st,
                cc,
                ac,
                wc,
                lc,
            )
            return True
        except Exception as exc:
            logger.exception(f"❌ Erreur sauvegarde état {self.id}: {exc}")
            return False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # P3: Queue attachment (called by OrchestratorAsync after subscribe)
    # ------------------------------------------------------------------

    def attach_queue(self, queue: Any) -> None:
        """
        Attach an :class:`~instance_queue.InstanceQueue` to this instance.

        Must be called *before* :meth:`start` so the consumer task is
        started during instance startup.

        Args:
            queue: :class:`InstanceQueue` provided by :class:`AsyncDispatcher`.
        """
        self._instance_queue = queue
        logger.debug(f"📬 Queue attachée à {self.id}")

    # P4: Hot-path optimizer injection
    def attach_hot_optimizer(self, optimizer: Any) -> None:
        """
        Attach a :class:`~hot_path_optimizer.HotPathOptimizer` for latency
        telemetry on the hot path.

        Optional — if not called, latency measurement is skipped and the hot
        path runs without any instrumentation overhead.

        Args:
            optimizer: :class:`HotPathOptimizer` provided by the orchestrator.
        """
        self._hot_optimizer = optimizer
        logger.debug(f"⚡ HotPathOptimizer attaché à {self.id}")

    async def start_queue_consumer(self) -> None:
        """
        Start the dedicated asyncio.Task that consumes from the attached queue.

        Called automatically by :meth:`start` when a queue has been attached.
        Safe to call explicitly for unit testing.

        Raises:
            RuntimeError: If no queue has been attached via :meth:`attach_queue`.
        """
        if self._instance_queue is None:
            raise RuntimeError(
                f"Instance {self.id}: no queue attached — call attach_queue() first"
            )
        if self._queue_consumer_task and not self._queue_consumer_task.done():
            return  # Already running
        self._queue_consumer_task = asyncio.create_task(
            self._queue_consumer_loop(),
            name=f"queue-consumer-{self.id}",
        )
        logger.debug(f"📬 Consumer task démarrée: {self.id}")

    async def _queue_consumer_loop(self) -> None:
        """
        Async loop that consumes ticks from the attached :class:`InstanceQueue`.

        Replaces the direct ``on_price_update`` callback used in P2.

        Design:
            - Blocks on ``await queue.get()`` — O(1) await, no spin.
            - Calls ``on_price_update`` for each tick.
            - On ``CancelledError``: stop consuming, do NOT drain.
              The drain happens in :meth:`stop` after the task is cancelled.
            - Errors in ``on_price_update`` are caught and logged; the
              consumer loop continues (resilience > crash).
        """
        queue = self._instance_queue
        logger.debug(f"📬 _queue_consumer_loop démarrée: {self.id}")
        try:
            while True:
                data = await queue.get()
                try:
                    await self.on_price_update(data)
                except Exception as exc:
                    logger.error(
                        f"❌ Erreur on_price_update {self.id}: {exc}",
                        exc_info=True,
                    )
        except asyncio.CancelledError:
            logger.debug(f"📬 _queue_consumer_loop arrêtée: {self.id}")
            raise

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self.status == InstanceStatus.RUNNING:
            return
        self.status = InstanceStatus.RUNNING
        self._start_time = datetime.now(timezone.utc)
        await self.recover_state()
        await self.save_state()
        self._init_strategy()

        # P3: if a queue is attached, start the consumer task
        if self._instance_queue is not None:
            await self.start_queue_consumer()

        logger.info(f"▶️ Instance {self.id} démarrée (async)")

    async def stop(self) -> None:
        """
        Graceful shutdown:
            1. Set status STOPPING (no new positions accepted).
            2. Cancel the queue consumer task (if any).
            3. Drain the queue (discard remaining ticks).
            4. Save state and set status STOPPED.
        """
        logger.info(f"⏹️ Arrêt instance {self.id}...")
        self.status = InstanceStatus.STOPPING

        # Cancel queue consumer task
        if self._queue_consumer_task and not self._queue_consumer_task.done():
            self._queue_consumer_task.cancel()
            try:
                await self._queue_consumer_task
            except asyncio.CancelledError:
                pass
        self._queue_consumer_task = None

        # Drain remaining ticks from queue
        if self._instance_queue is not None:
            drained = await self._instance_queue.drain()
            if drained:
                logger.debug(f"📬 {self.id}: {drained} tick(s) drainés à l'arrêt")

        self.status = InstanceStatus.STOPPED
        await self.save_state()
        logger.info(f"✅ Instance {self.id} arrêtée (async)")

    def pause(self) -> None:
        self.status = InstanceStatus.PAUSED

    def resume(self) -> None:
        self.status = InstanceStatus.RUNNING

    async def emergency_stop(self) -> None:
        logger.warning(f"🚨 ARRÊT URGENCE instance {self.id}")
        async with self._lock:
            self.status = InstanceStatus.STOPPED
        await self.save_state()

    # ------------------------------------------------------------------
    # Strategy init (sync — strategies are mostly CPU-bound)
    # ------------------------------------------------------------------

    def _init_strategy(self) -> None:
        """Initialize strategy. Strategies use async on_price."""
        strategy_name = self.config.strategy
        if strategy_name == "grid":
            from .strategies.grid_async import GridStrategyAsync
            self._strategy = GridStrategyAsync(self)
        elif strategy_name == "trend":
            from .strategies.trend_async import TrendStrategyAsync
            self._strategy = TrendStrategyAsync(self)
        else:
            logger.warning(f"⚠️ Stratégie inconnue: {strategy_name}, fallback Grid")
            from .strategies.grid_async import GridStrategyAsync
            self._strategy = GridStrategyAsync(self)

        from .signal_handler_async import SignalHandlerAsync
        self._signal_handler = SignalHandlerAsync(
            self, order_executor=self._order_executor
        )
        self._on_position_close = self._notify_strategy_position_closed
        logger.info(f"🎯 Stratégie {strategy_name} chargée pour {self.id} (async)")

    def _notify_strategy_position_closed(self, instance: Any, position: Any) -> None:
        if self._strategy and hasattr(self._strategy, "on_position_closed"):
            try:
                self._strategy.on_position_closed(position, position.profit or 0.0)
            except Exception as exc:
                logger.exception(f"❌ Erreur notification stratégie: {exc}")

    # ------------------------------------------------------------------
    # Price update (async — called from WS multiplexer)
    # ------------------------------------------------------------------

    def _validate_price(self, price: float) -> bool:
        """
        C1/C5 guard: reject invalid, non-finite, or suspiciously large price jumps.

        Returns True and updates self._last_price if the price is valid.
        Returns False (and logs) without touching state if invalid.
        """
        if not math.isfinite(price) or price <= 0:
            logger.warning(f"❌ Prix invalide reçu: {price}")
            return False
        if self._last_price is not None and self._last_price > 0:
            if abs(price - self._last_price) / self._last_price > 0.10:
                logger.warning(f"⚠️ Variation anormale: {self._last_price} → {price}")
                return False
        self._last_price = price
        return True

    async def on_price_update(self, data: TickerData) -> None:
        """
        Hot path: called on every price tick from the WebSocket feed.

        P4 invariants:
            - Zero asyncio.Lock (asyncio is single-threaded — direct attribute
              writes have no await between them and are therefore atomic).
            - Zero I/O (no SQLite, no network).
            - Zero per-tick allocation (data.timestamp reused from TickerData;
              deque.append is O(1) with no object creation).
            - check_leverage_downgrade() removed — moved to the cold path via
              ColdPathScheduler.schedule_periodic() in the orchestrator.

        Latency telemetry is gated on self._hot_optimizer so instances without
        an attached optimizer incur zero overhead.
        """
        opt = self._hot_optimizer
        t0 = opt.start_tick() if opt is not None else 0

        # C1/C5: reject invalid prices before any downstream computation.
        # _last_price is updated as a side-effect of _validate_price().
        if not self._validate_price(data.price):
            return

        # Reuse timestamp from TickerData (set once per WS message, not per instance)
        self._price_history.append((data.timestamp, data.price))

        if self._strategy is not None and self.status == InstanceStatus.RUNNING:
            # Strategy.on_price is sync (CPU-bound, no I/O)
            self._strategy.on_price(data.price)

        if opt is not None:
            opt.record_tick(t0)

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    async def open_position(
        self,
        price: float,
        volume: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        stop_loss_txid: Optional[str] = None,
        buy_txid: Optional[str] = None,
    ) -> Optional[Position]:
        """Open a position (atomic check+create under lock)."""
        order_value = price * volume
        position_id = str(uuid.uuid4())[:8]

        async with self._lock:
            available = self._current_capital - self._allocated_capital
            if not (
                self.status == InstanceStatus.RUNNING
                and available >= order_value
                and len(self._positions) < 10
            ):
                return None

            position = Position(
                id=position_id,
                buy_price=price,
                volume=volume,
                stop_loss=stop_loss,
                take_profit=take_profit,
                stop_loss_txid=stop_loss_txid,
                buy_txid=buy_txid,
            )
            self._positions[position_id] = position
            self._allocated_capital += order_value

        logger.info(
            f"📈 Position ouverte {self.id}/{position_id}: {volume} @ {price:.2f}€"
        )

        # Persistence (non-blocking)
        await self._run_sync(
            self._persistence.save_position,
            position_id,
            self.id,
            price,
            volume,
            "open",
            self.config.strategy,
            {
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "stop_loss_txid": stop_loss_txid,
                "buy_txid": buy_txid,
            },
        )

        if self._on_position_open:
            self._on_position_open(self, position)

        await self.save_state()
        return position

    async def close_position(
        self,
        position_id: str,
        sell_price: float,
        sell_txid: Optional[str] = None,
    ) -> Optional[float]:
        """Close a position and compute P&L."""
        async with self._lock:
            if position_id not in self._positions:
                return None
            position = self._positions[position_id]
            if position.status not in ("open", "closing"):
                return None

            gross_profit = (sell_price - position.buy_price) * position.volume

            if self._fee_optimizer:
                maker_pct, taker_pct = self._fee_optimizer.get_fees()
            else:
                maker_pct, taker_pct = 0.25, 0.40

            buy_fee = position.buy_price * position.volume * (maker_pct / 100.0)
            sell_fee = sell_price * position.volume * (taker_pct / 100.0)
            net_profit = gross_profit - buy_fee - sell_fee

            position.sell_price = sell_price
            position.status = "closed"
            position.close_time = datetime.now(timezone.utc)
            position.profit = net_profit
            position.sell_txid = sell_txid

            self._current_capital += net_profit
            self._allocated_capital -= position.buy_price * position.volume

            if net_profit > 0:
                self._win_count += 1
                self._win_streak += 1
            else:
                self._loss_count += 1
                self._win_streak = 0

            if self._current_capital > self._peak_capital:
                self._peak_capital = self._current_capital
            else:
                dd = (self._peak_capital - self._current_capital) / self._peak_capital
                self._max_drawdown = max(self._max_drawdown, dd)

            position_copy = position
            profit_copy = net_profit

        logger.info(
            f"📉 Position fermée {self.id}/{position_id}: Profit {net_profit:.2f}€"
        )

        await self._run_sync(
            self._persistence.close_position_and_record_trade,
            position_id,
            {
                "instance_id": self.id,
                "side": "sell",
                "price": sell_price,
                "volume": position_copy.volume,
                "profit": profit_copy,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        if self._on_position_close:
            self._on_position_close(self, position_copy)

        await self.save_state()
        return profit_copy

    def record_spin_off(self, amount: float) -> None:
        # This is called rarely; we can use sync-ish pattern here
        self._current_capital -= amount

    # ------------------------------------------------------------------
    # Leverage (sync — pure computation, no I/O)
    # ------------------------------------------------------------------

    def activate_leverage(self, leverage: int) -> bool:
        if self._current_capital >= 1000:
            self.config.leverage = leverage
            return True
        return False

    def activate_leverage_level(        self,
        level: LeverageLevel,
        human_approved: bool = False,
    ) -> Dict[str, Any]:
        """Activate leverage with strict checks (identical to sync version)."""
        if level == LeverageLevel.X1:
            self.config.leverage = 1
            self._leverage_level = LeverageLevel.X1
            return {"success": True, "level": 1, "reason": "Levier X1 activé"}

        current_dd = self.get_drawdown() * 100
        trend = self.detect_trend()
        pf_30 = self._compute_profit_factor_days(30)
        pf_60 = self._compute_profit_factor_days(60)
        current_level = self._leverage_level.value

        if level == LeverageLevel.X2:
            checks = []
            if pf_30 < 2.0:
                checks.append(f"PF 30j = {pf_30:.2f} (requis > 2.0)")
            if trend != "range":
                checks.append(f"Marché {trend} (requis range-bound)")
            if current_dd >= 5.0:
                checks.append(f"DD = {current_dd:.1f}% (requis < 5%)")
            if checks:
                return {"success": False, "level": current_level, "reason": "; ".join(checks)}
            self.config.leverage = 2
            self._leverage_level = LeverageLevel.X2
            return {"success": True, "level": 2, "reason": "Levier X2 activé"}

        if level == LeverageLevel.X3:
            checks = []
            if pf_60 < 2.5:
                checks.append(f"PF 60j = {pf_60:.2f} (requis > 2.5)")
            if current_dd >= 3.0:
                checks.append(f"DD = {current_dd:.1f}% (requis < 3%)")
            if not human_approved:
                checks.append("Validation humaine manquante")
            if checks:
                return {"success": False, "level": current_level, "reason": "; ".join(checks)}
            self.config.leverage = 3
            self._leverage_level = LeverageLevel.X3
            return {"success": True, "level": 3, "reason": "Levier X3 activé"}

        return {"success": False, "level": current_level, "reason": f"Niveau inconnu: {level}"}

    def _compute_profit_factor_days(self, days: int) -> float:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        gross_profit = 0.0
        gross_loss = 0.0
        for trade in self._trades:
            t = trade.timestamp if isinstance(trade.timestamp, datetime) else datetime.now(timezone.utc)
            if t < cutoff:
                continue
            p = trade.profit if trade.profit is not None else 0.0
            if p > 0:
                gross_profit += p
            elif p < 0:
                gross_loss += abs(p)
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    def check_leverage_downgrade(self) -> Optional[Dict[str, Any]]:
        current_level = self._leverage_level
        if current_level == LeverageLevel.X1:
            return None
        current_dd = self.get_drawdown() * 100
        trend = self.detect_trend()

        if current_level == LeverageLevel.X3:
            pf_60 = self._compute_profit_factor_days(60)
            reasons = []
            if pf_60 < 2.5:
                reasons.append(f"PF 60j={pf_60:.2f} < 2.5")
            if current_dd > 3.0:
                reasons.append(f"DD={current_dd:.1f}% > 3%")
            if reasons:
                self.config.leverage = 2
                self._leverage_level = LeverageLevel.X2
                return {"downgraded": True, "from": "X3", "to": "X2", "reason": ", ".join(reasons)}

        if current_level == LeverageLevel.X2:
            pf_30 = self._compute_profit_factor_days(30)
            reasons = []
            if pf_30 < 2.0:
                reasons.append(f"PF 30j={pf_30:.2f} < 2.0")
            if current_dd > 5.0:
                reasons.append(f"DD={current_dd:.1f}% > 5%")
            if trend in ("up", "down"):
                reasons.append(f"tendance forte ({trend})")
            if reasons:
                self.config.leverage = 1
                self._leverage_level = LeverageLevel.X1
                return {"downgraded": True, "from": "X2", "to": "X1", "reason": ", ".join(reasons)}

        return None

    # ------------------------------------------------------------------
    # Getters (sync — pure reads, no I/O)
    # ------------------------------------------------------------------

    def get_current_capital(self) -> float:
        return self._current_capital

    def get_available_capital(self) -> float:
        return self._current_capital - self._allocated_capital

    def get_initial_capital(self) -> float:
        return self._initial_capital

    def get_profit(self) -> float:
        return self._current_capital - self._initial_capital

    def get_win_streak(self) -> int:
        return self._win_streak

    def get_drawdown(self) -> float:
        if self._peak_capital > 0:
            return (self._peak_capital - self._current_capital) / self._peak_capital
        return 0.0

    def get_max_drawdown(self) -> float:
        return self._max_drawdown

    def get_volatility(self) -> float:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = [p for t, p in self._price_history if t > cutoff]
        if len(recent) < 2:
            return 0.0
        mean = sum(recent) / len(recent)
        variance = sum((p - mean) ** 2 for p in recent) / len(recent)
        return (variance ** 0.5) / mean if mean > 0 else 0.0

    def detect_trend(self) -> str:
        if len(self._price_history) < 20:
            return "unknown"
        prices = [p for _, p in self._price_history]
        ma_short = sum(prices[-10:]) / min(10, len(prices[-10:]))
        ma_long = sum(prices[-30:]) / min(30, len(prices[-30:]))
        threshold = 0.005
        if ma_short > ma_long * (1 + threshold):
            return "up"
        elif ma_short < ma_long * (1 - threshold):
            return "down"
        return "range"

    def is_running(self) -> bool:
        return self.status == InstanceStatus.RUNNING

    def get_leverage_level(self) -> LeverageLevel:
        return self._leverage_level

    def get_open_position_ids(self) -> List[str]:
        return [pid for pid, p in self._positions.items() if p.status == "open"]

    def get_positions_snapshot(self) -> List[Dict]:
        last_price = self._last_price
        snapshot = []
        for pos_id, pos in list(self._positions.items()):
            cp = last_price or pos.buy_price
            pnl = (cp - pos.buy_price) * pos.volume
            pnl_pct = (cp - pos.buy_price) / pos.buy_price * 100 if pos.buy_price > 0 else 0
            snapshot.append({
                "id": pos_id,
                "pair": self.config.symbol,
                "side": "LONG",
                "size": f"{pos.volume:.6f}",
                "volume": pos.volume,
                "entry_price": pos.buy_price,
                "current_price": cp,
                "pnl": pnl,
                "pnl_percent": pnl_pct,
                "status": pos.status,
                "buy_txid": pos.buy_txid,
                "txid": pos.buy_txid,
                "stop_loss_txid": pos.stop_loss_txid,
                "sell_txid": pos.sell_txid,
            })
        return snapshot

    def get_status(self) -> Dict[str, Any]:
        positions_copy = list(self._positions.values())
        return {
            "id": self.id,
            "name": self.config.name,
            "status": self.status.value,
            "strategy": self.config.strategy,
            "initial_capital": self._initial_capital,
            "current_capital": self._current_capital,
            "total_profit": self.get_profit(),
            "profit_pct": (self.get_profit() / self._initial_capital * 100) if self._initial_capital else 0,
            "win_streak": self._win_streak,
            "drawdown": self.get_drawdown(),
            "max_drawdown": self._max_drawdown,
            "open_positions_count": len([p for p in positions_copy if p.status == "open"]),
            "leverage": self.config.leverage,
            "trend": self.detect_trend(),
            "last_price": self._last_price,
        }

    def _map_to_kraken_symbol(self, symbol: str) -> str:
        return self._KRAKEN_SYMBOL_MAP.get(symbol, symbol)

    async def on_stop_loss_triggered(self, position_id: str, sell_price: float) -> None:
        logger.warning(f"🛑 Stop-loss déclenché {self.id}/{position_id} @ {sell_price:.2f}€")
        profit = await self.close_position(position_id, sell_price)
        if profit is not None:
            logger.info(f"   Position fermée par SL, P&L: {profit:.2f}€")
        if self._strategy and hasattr(self._strategy, "on_position_closed"):
            pos = self._positions.get(position_id)
            if pos:
                try:
                    self._strategy.on_position_closed(pos, profit or 0.0)
                except Exception as exc:
                    logger.exception(f"❌ Erreur notification stratégie: {exc}")

    def recalculate_allocated_capital(self) -> float:
        calculated = sum(
            pos.buy_price * pos.volume
            for pos in self._positions.values()
            if pos.status == "open"
        )
        if abs(self._allocated_capital - calculated) > 0.01:
            self._allocated_capital = calculated
        return self._allocated_capital

    def get_last_trade_time(self) -> datetime:
        """
        Return the time of the most recent closed position, or instance start time.

        Used by the orchestrator to detect idle instances (no trades for >N hours).
        Falls back to _start_time (set when status becomes RUNNING).
        """
        last = None
        for pos in self._positions.values():
            if pos.close_time is not None:
                if last is None or pos.close_time > last:
                    last = pos.close_time
        if last is not None:
            return last
        # No closed positions: use the time the instance started
        return getattr(self, '_start_time', None) or datetime.now(timezone.utc)

    def get_market_quality(self) -> Optional[int]:
        """
        Return the market quality score for this instance's symbol.

        Returns the MarketQualityScore.value (int 1-5) or None if analysis
        unavailable.  Used by the orchestrator for culling decisions.
        """
        try:
            from .market_analyzer import get_market_analyzer
            analyzer = get_market_analyzer()
            metrics = analyzer.analyze_market(self.config.symbol)
            if metrics:
                return metrics.market_quality.value
        except Exception:
            pass
        return None
