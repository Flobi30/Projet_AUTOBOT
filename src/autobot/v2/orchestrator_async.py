"""
Orchestrator — Full Async + uvloop
MIGRATION P0: Replaces orchestrator.py (threading)

Central async controller for all trading instances.
Uses:
- asyncio event loop (uvloop if available) instead of threads
- asyncio.Lock instead of threading.Lock
- asyncio.Event instead of threading.Event
- asyncio.create_task instead of Thread()
- asyncio.sleep instead of time.sleep

Public API identical to Orchestrator (with async/await).
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

from .ring_buffer_dispatcher import RingBufferDispatcher
from .async_dispatcher import AsyncDispatcher
from .websocket_async import TickerData
from .instance_async import TradingInstanceAsync
from .order_executor_async import OrderExecutorAsync, get_order_executor_async
try:
    from .paper_trading_fix import PaperTradingExecutor
except ImportError:
    PaperTradingExecutor = None
from .order_router import OrderRouter, get_order_router, OrderPriority
from .stop_loss_manager_async import StopLossManagerAsync
from .reconciliation_async import ReconciliationManagerAsync
from .validator import ValidatorEngine, ValidationResult, ValidationStatus
from .orchestrator import InstanceConfig  # Reuse config dataclass
from .risk_manager import get_risk_manager
from .persistence import get_persistence
from .hot_path_optimizer import HotPathOptimizer, get_hot_path_optimizer
from .cold_path_scheduler import ColdPathScheduler, get_cold_path_scheduler
from .module_manager import ModuleManager

logger = logging.getLogger(__name__)


def _get_available_capital_real(
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
) -> float:
    """Get available capital from Kraken API (sync — called via run_in_executor)."""
    key = api_key or os.getenv("KRAKEN_API_KEY")
    secret = api_secret or os.getenv("KRAKEN_API_SECRET")
    if not key or not secret:
        return 0.0
    try:
        import krakenex
        k = krakenex.API(key=key, secret=secret)
        k.session.timeout = 10
        response = k.query_private("Balance")
        if "result" in response:
            return float(response["result"].get("ZEUR", 0))
        return 0.0
    except Exception:
        return 0.0


class OrchestratorAsync:
    """
    Async orchestrator — manages all trading instances.

    Drop-in async replacement for Orchestrator.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        # SEC-01: store API credentials — do NOT log these values
        self.api_key = api_key
        self.api_secret = api_secret

        # Order executor (async) — PaperTrading si PAPER_TRADING=true
        import os as _os
        self.paper_mode = _os.getenv("PAPER_TRADING", "false").lower() == "true"
        
        if self.paper_mode and PaperTradingExecutor is not None:
            initial_capital = float(_os.getenv("INITIAL_CAPITAL", "1000.0"))
            self.order_executor = PaperTradingExecutor(
                db_path="data/paper_trades.db",
                initial_capital=initial_capital,
            )
            logger.info(f"🎮 MODE PAPER TRADING (capital: {initial_capital:.0f}€)")
        else:
            self.order_executor = get_order_executor_async(api_key, api_secret)
            logger.info("🔴 MODE LIVE TRADING")

        # Stop-loss manager (async)
        self.stop_loss_manager = StopLossManagerAsync(self.order_executor)

        # P2: Ring buffer dispatcher (WebSocket → per-pair RingBuffers)
        self.ring_dispatcher = RingBufferDispatcher(api_key, api_secret)
        self.ws_client = self.ring_dispatcher  # Alias for is_connected() / stats

        # P3: Async dispatcher (RingBuffers → per-instance asyncio.Queues)
        self.async_dispatcher = AsyncDispatcher(self.ring_dispatcher)

        # P4: Hot/Cold path separation
        self.hot_optimizer: HotPathOptimizer = get_hot_path_optimizer()
        self.cold_scheduler: ColdPathScheduler = get_cold_path_scheduler()

        # Consumer tasks — one asyncio.Task per instance (queue consumption)
        # In P3 these are owned by TradingInstanceAsync._queue_consumer_task;
        # we keep a reference here only for coordinated cancellation on stop().
        self._consumer_tasks: Dict[str, asyncio.Task] = {}

        # Validator
        self.validator = ValidatorEngine()

        # Instances
        self._instances: Dict[str, TradingInstanceAsync] = {}
        # ARCH-01: protect _instances dict mutations across concurrent coroutines
        self._instances_lock = asyncio.Lock()

        # Reconciliation
        self.reconciliation_manager: Optional[ReconciliationManagerAsync] = None

        # Config
        self.config = {
            "max_instances": 2000,  # Target: 2000+ instances
            "spin_off_threshold": 2000.0,
            "leverage_threshold": 1000.0,
            "check_interval": 30,  # minutes
            "max_drawdown_global": 0.30,
        }

        # State
        self.running = False
        self._main_task: Optional[asyncio.Task] = None
        self._start_time: Optional[datetime] = None

        # Callbacks
        self._on_instance_created: Optional[Callable] = None
        self._on_instance_spinoff: Optional[Callable] = None
        self._on_alert: Optional[Callable] = None

        # Circuit breaker
        self._setup_circuit_breaker()

        # Market selector (reuse sync version)
        try:
            from .market_selector import get_market_selector
            self.market_selector = get_market_selector(self)
        except Exception:
            self.market_selector = None

        # Module manager -- conditional activation of all optional modules
        self.module_manager = ModuleManager()
        self.module_manager.init_modules(self)

        logger.info("🎛️ OrchestratorAsync initialisé (target: 2000+ instances)")

    # SEC-01: safe repr — never expose raw API keys in logs/repr
    def __repr__(self) -> str:
        key_hint = f"...{self.api_key[-4:]}" if self.api_key else "None"
        return f"OrchestratorAsync(api_key={key_hint!r}, instances={len(self._instances)})"

    def _setup_circuit_breaker(self) -> None:
        async def on_cb() -> None:
            logger.error("🚨 CIRCUIT BREAKER: Arrêt d'urgence!")
            await self.emergency_stop_all()

        self.order_executor.set_circuit_breaker_callback(on_cb)

    # ------------------------------------------------------------------
    # Instance management
    # ------------------------------------------------------------------

    async def create_instance(self, config: InstanceConfig) -> Optional[TradingInstanceAsync]:
        """Create a new trading instance."""
        # ARCH-02: check system resources before accepting a new instance
        try:
            import psutil
            mem = psutil.virtual_memory()
            if mem.percent > 90:
                logger.warning(
                    f"Memoire systeme critique ({mem.percent:.0f}%) -- instance refusee"
                )
                return None
        except ImportError:
            pass  # psutil optionnel

        if len(self._instances) >= self.config["max_instances"]:
            logger.warning(f"⚠️ Limite instances: {self.config['max_instances']}")
            return None

        instance_id = str(uuid.uuid4())[:8]
        instance = TradingInstanceAsync(
            instance_id=instance_id,
            config=config,
            orchestrator=self,
            order_executor=self.order_executor,
        )

        # ARCH-01: protect dict mutation with lock
        async with self._instances_lock:
            self._instances[instance_id] = instance

        if len(self._instances) > 1000:
            logger.warning(f"⚠️ {len(self._instances)} instances actives")

        # P3: Subscribe via AsyncDispatcher — creates InstanceQueue + ring reader
        queue = await self.async_dispatcher.subscribe(config.symbol, instance_id)

        # Attach queue to instance (consumer task started in instance.start())
        instance.attach_queue(queue)

        # P4: Attach shared hot-path optimizer for latency telemetry
        instance.attach_hot_optimizer(self.hot_optimizer)

        logger.info(
            f"✅ Instance créée: {instance_id} ({config.name}) - "
            f"Capital: {config.initial_capital:.2f}€"
        )

        if self._on_instance_created:
            self._on_instance_created(instance)

        return instance

    async def remove_instance(self, instance_id: str) -> bool:
        # ARCH-01: protect dict mutation with lock
        async with self._instances_lock:
            if instance_id not in self._instances:
                return False
            instance = self._instances.pop(instance_id)

        # P3: Unsubscribe from AsyncDispatcher (cancels queue, not ring reader
        # unless last subscriber for that pair)
        self.async_dispatcher.unsubscribe(instance_id)

        # instance.stop() drains the queue and cancels the consumer task
        await instance.stop()
        logger.info(f"🗑️ Instance supprimée: {instance_id}")
        return True

    async def create_instance_auto(
        self, parent_instance_id: Optional[str] = None
    ) -> Optional[TradingInstanceAsync]:
        """Create instance with auto market selection."""
        if not self.market_selector:
            return None
        selection = self.market_selector.select_market_for_spinoff(parent_instance_id or "auto")
        if not selection:
            return None
        config = InstanceConfig(
            name=f"Auto-{selection.symbol.replace('/', '-')} ({selection.strategy})",
            symbol=selection.symbol,
            strategy=selection.strategy,
            initial_capital=0,
            leverage=1,
            grid_config={"range_percent": 7.0, "num_levels": 15},
        )
        return await self.create_instance(config)

    # ------------------------------------------------------------------
    # Spin-off & leverage
    # ------------------------------------------------------------------

    async def check_spin_off(self, parent: TradingInstanceAsync) -> Optional[TradingInstanceAsync]:
        capital = parent.get_current_capital()
        context = {
            "capital": capital,
            "threshold": self.config["spin_off_threshold"],
            "available_capital": await self._get_available_capital(),
            "min_capital": 500.0,
            "instance_count": len(self._instances),
            "max_instances": self.config["max_instances"],
            "volatility": parent.get_volatility(),
            "max_volatility": 0.10,
        }
        result = self.validator.validate("spin_off", context)
        if result.status == ValidationStatus.GREEN:
            new = await self.create_instance_auto(parent.id)
            if new:
                parent.record_spin_off(500.0)
                logger.info(f"🔄 Spin-off: {parent.id} → {new.id}")
                if self._on_instance_spinoff:
                    self._on_instance_spinoff(parent, new)
                return new
        return None

    def check_leverage_activation(self, instance: TradingInstanceAsync) -> bool:
        capital = instance.get_current_capital()
        if capital < self.config["leverage_threshold"]:
            return False
        context = {
            "capital": capital,
            "threshold": self.config["leverage_threshold"],
            "win_streak": instance.get_win_streak(),
            "min_win_streak": 5,
            "drawdown": instance.get_drawdown(),
            "max_drawdown": 0.10,
            "trend": instance.detect_trend(),
        }
        result = self.validator.validate("leverage", context)
        if result.status in (ValidationStatus.GREEN, ValidationStatus.YELLOW):
            if instance.activate_leverage(2):
                return True
        return False

    async def _get_available_capital(self) -> float:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, _get_available_capital_real, self.api_key, self.api_secret
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _main_loop(self) -> None:
        logger.info("🚀 OrchestratorAsync main loop démarré")
        while self.running:
            try:
                instances = list(self._instances.values())
                for inst in instances:
                    if not inst.is_running():
                        continue
                    await self.check_spin_off(inst)
                    if inst.config.leverage == 1:
                        self.check_leverage_activation(inst)
                    if inst.get_drawdown() > self.config["max_drawdown_global"]:
                        logger.error(f"🚨 Drawdown critique: {inst.id}")
                        await inst.emergency_stop()
                        if self._on_alert:
                            self._on_alert("CRITICAL_DRAWDOWN", inst)

                await self._check_global_health()
                await asyncio.sleep(self.config["check_interval"] * 60)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"❌ Erreur main loop: {exc}")
                await asyncio.sleep(60)

    async def _check_global_health(self) -> None:
        if not self.ws_client.is_connected():
            logger.warning("🔌 WS déconnecté, reconnexion...")
            try:
                await self.ring_dispatcher.connect()
            except Exception as exc:
                logger.error(f"❌ Reconnexion échouée: {exc}")

        active = [i for i in self._instances.values() if i.is_running()]
        if active:
            rm = get_risk_manager()
            rm.set_orchestrator(self)
            await rm.check_global_risk(active)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._start_time = datetime.now(timezone.utc)

        # Cleanup orphaned instance_state records at startup
        try:
            persistence = get_persistence()
            deleted = persistence.cleanup_orphaned_instances()
            if deleted:
                logger.info(f"🧹 Startup cleanup: {deleted} orphaned instances removed")
        except Exception as exc:
            logger.warning(f"⚠️ Startup cleanup failed: {exc}")

        # P4: Disable GC for the hot path — periodic collection via cold scheduler
        self.hot_optimizer.enter_hot_path()

        # P4: Start cold-path scheduler
        await self.cold_scheduler.start()

        # P4: Periodic GC every 30 s (reclaims memory while hot path is GC-free)
        self.cold_scheduler.schedule_gc(self.hot_optimizer, interval=30.0)

        # P4: Periodic leverage-downgrade check for all instances every 60 s
        self.cold_scheduler.schedule_periodic(
            self._check_leverage_all_instances,
            interval=60.0,
            name="leverage-downgrade",
        )

        # Connect WS via ring dispatcher (P2)
        await self.ring_dispatcher.connect()

        # Start P3 async dispatcher (starts per-pair dispatch tasks)
        await self.async_dispatcher.start()

        # Start SL manager
        await self.stop_loss_manager.start(
            on_stop_loss_triggered=self._on_stop_loss_triggered
        )

        # Start reconciliation — ARCH-06: pass callable for dynamic snapshot
        self.reconciliation_manager = ReconciliationManagerAsync(
            order_executor=self.order_executor,
            instances=lambda: dict(self._instances),
        )
        await self.reconciliation_manager.start()

        # Start optional modules (DailyReporter, RebalanceManager, etc.)
        await self.module_manager.start()

        # Start instances
        for inst in list(self._instances.values()):
            await inst.start()

        # Main loop
        self._main_task = asyncio.create_task(self._main_loop())
        logger.info("✅ OrchestratorAsync démarré (P4: hot/cold path actif)")

    def _check_leverage_all_instances(self) -> None:
        """
        Cold-path periodic task: run leverage downgrade checks for all instances.

        Previously called per-tick inside on_price_update() (P0 behaviour).
        P4 moves it here — runs every 60 s via ColdPathScheduler, keeping the
        hot path free of O(N_trades) computation.
        """
        for inst in list(self._instances.values()):
            if inst.is_running():
                try:
                    inst.check_leverage_downgrade()
                except Exception as exc:
                    logger.error(
                        f"❄️ Erreur check_leverage {inst.id}: {exc}", exc_info=True
                    )

    async def _on_stop_loss_triggered(self, position_id: str, order_status: Any) -> None:
        for inst in self._instances.values():
            positions = inst.get_positions_snapshot()
            for pos in positions:
                if pos.get("id") == position_id:
                    sell_price = getattr(order_status, "avg_price", None) or getattr(order_status, "price", None)
                    if sell_price:
                        await inst.on_stop_loss_triggered(position_id, sell_price)
                    return

    async def stop(self) -> None:
        logger.info("🛑 Arrêt OrchestratorAsync...")
        self.running = False

        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass

        for inst in list(self._instances.values()):
            await inst.stop()  # Each instance drains its queue + cancels consumer task

        # P3: Stop async dispatcher (cancels dispatch tasks, drains all queues)
        await self.async_dispatcher.stop()

        await self.ring_dispatcher.disconnect()
        await self.stop_loss_manager.stop()

        if self.reconciliation_manager:
            await self.reconciliation_manager.stop()

        # Stop optional modules
        await self.module_manager.stop()

        await self.order_executor.close()

        # P4: Stop cold scheduler then re-enable GC
        await self.cold_scheduler.stop()
        self.hot_optimizer.exit_hot_path()

        logger.info(
            "✅ OrchestratorAsync arrêté — "
            f"hot path stats: {self.hot_optimizer.stats}"
        )

    async def emergency_stop_all(self) -> None:
        logger.error("🚨🚨🚨 EMERGENCY STOP ALL!")
        stopped = 0
        for inst in list(self._instances.values()):
            try:
                await inst.emergency_stop()
                stopped += 1
            except Exception as exc:
                logger.exception(f"❌ Erreur arrêt {inst.id}: {exc}")
        logger.error(f"🚨 {stopped}/{len(self._instances)} arrêtées")
        if self._on_alert:
            self._on_alert("EMERGENCY_STOP_ALL", None)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict:
        return {
            "running": self.running,
            "start_time": self._start_time,
            "uptime": datetime.now(timezone.utc) - self._start_time if self._start_time else None,
            "uptime_seconds": (datetime.now(timezone.utc) - self._start_time).total_seconds() if self._start_time else None,
            "instance_count": len(self._instances),
            "max_instances": self.config["max_instances"],
            "websocket_connected": self.ws_client.is_connected(),
            "modules": self.module_manager.get_status() if self.module_manager else {},
            "instances": [
                {
                    "id": i.id,
                    "name": i.config.name,
                    "capital": i.get_current_capital(),
                    "running": i.is_running(),
                }
                for i in self._instances.values()
            ],
        }

    def get_instances_snapshot(self) -> List[Dict]:
        snapshot = []
        for inst_id, inst in self._instances.items():
            try:
                s = inst.get_status()
                snapshot.append({
                    "id": inst_id,
                    "name": s["name"],
                    "capital": s["current_capital"],
                    "profit": s["total_profit"],
                    "status": s["status"],
                    "strategy": s["strategy"],
                    "open_positions": s["open_positions_count"],
                })
            except Exception:
                pass
        return snapshot

    def set_callbacks(
        self,
        on_instance_created: Optional[Callable] = None,
        on_instance_spinoff: Optional[Callable] = None,        on_alert: Optional[Callable] = None,
    ) -> None:
        self._on_instance_created = on_instance_created
        self._on_instance_spinoff = on_instance_spinoff
        self._on_alert = on_alert
