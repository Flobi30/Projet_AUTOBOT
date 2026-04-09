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
from datetime import datetime, timezone, timedelta
from time import perf_counter
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
from .modules.trailing_stop_atr import TrailingStopATR
from .modules.black_swan import BlackSwanCatcher
from .modules.volatility_weighter import VolatilityWeighter
from .modules.pyramiding_manager import PyramidingManager
from .modules.kelly_criterion import KellyCriterion
from .modules.momentum_scoring import MomentumScorer
from .modules.xgboost_predictor import XGBoostPredictor
from .modules.sentiment_nlp import SentimentAnalyzer
from .modules.cnn_lstm_predictor import HeuristicPredictor
from .modules.onchain_data import OnchainDataModule
from .strategies.mean_reversion import MeanReversionStrategy
from .strategy_ensemble import StrategyEnsemble, MarketRegime
from .reports import DailyReporter
from .shadow_trading import ShadowTradingManager
from .strategies.adaptive_grid_config import get_default_registry
from .strategies.multi_grid_orchestrator import MultiGridOrchestrator
from .rebalance_manager import RebalanceManager
from .auto_evolution import AutoEvolutionManager
from .config import (
    HEALTH_SCORE_THRESHOLD,
    MAX_BACKOFF_SECONDS,
    MAX_INSTANCES_PER_CYCLE,
    MAX_REPEATED_AUTO_ACTIONS,
    MIN_PF_FOR_SPINOFF,
    SPIN_OFF_THRESHOLD,
    TARGET_VOLATILITY,
    TRADE_ACTION_MIN_INTERVAL_S,
    WEBSOCKET_STREAMS,
)

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    return value in ("1", "true", "yes", "on")


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
        # Modules de protection explicitement branchés (défense en profondeur)
        self.trailing_stops: Dict[str, TrailingStopATR] = {}
        self.pyramiding: Dict[str, PyramidingManager] = {}
        self.black_swan = BlackSwanCatcher()
        self.volatility_weighter = VolatilityWeighter()
        self.kelly_criterion = KellyCriterion(max_position_pct=0.25)
        self.mean_reversion: Dict[str, MeanReversionStrategy] = {}
        self.strategy_ensemble = StrategyEnsemble()
        self.momentum = MomentumScorer()
        self.xgboost = XGBoostPredictor()
        self.sentiment = SentimentAnalyzer()
        self.heuristic_predictor = HeuristicPredictor()
        self.onchain_data = OnchainDataModule()
        self.daily_reporter = DailyReporter(self)
        self._daily_report_task: Optional[asyncio.Task] = None
        self._xgboost_train_task: Optional[asyncio.Task] = None
        self._sentiment_task: Optional[asyncio.Task] = None
        self._shadow_promotion_task: Optional[asyncio.Task] = None
        self._rebalance_task: Optional[asyncio.Task] = None
        self._auto_evolution_task: Optional[asyncio.Task] = None
        self._rebalance_manager: Optional[RebalanceManager] = None
        self._auto_evolution_manager: Optional[AutoEvolutionManager] = None
        self._evolution_pf_baseline: Dict[str, float] = {}
        self._multi_grid: Dict[str, MultiGridOrchestrator] = {}
        self._multi_grid_symbol_owner: Dict[str, str] = {}
        self._pair_registry = get_default_registry()
        self._capital_ops_lock = asyncio.Lock()
        self._loop_metrics: Dict[str, float] = {
            "process_cycle_ms": 0.0,
            "signal_eval_ms": 0.0,
            "shadow_update_ms": 0.0,
        }
        self._decision_stats: Dict[str, int] = {
            "risk_blocks": 0,
            "exit_actions": 0,
            "entry_actions": 0,
            "add_actions": 0,
            "conflicts_resolved": 0,
        }
        self.autonomous_mode = _env_bool("AUTOBOT_AUTONOMOUS", True)
        self.decision_policy: Dict[str, int] = {
            "RISK_BLOCK": int(os.getenv("DECISION_PRIORITY_RISK_BLOCK", "100")),
            "EXIT": int(os.getenv("DECISION_PRIORITY_EXIT", "80")),
            "ENTRY": int(os.getenv("DECISION_PRIORITY_ENTRY", "50")),
            "ADD": int(os.getenv("DECISION_PRIORITY_ADD", "40")),
        }
        self._last_decision: Dict[str, Any] = {
            "instance_id": None,
            "action": "NONE",
            "priority": 0,
            "reason": "startup",
            "timestamp": None,
        }
        self.runtime_constraints: Dict[str, int] = {
            "max_instances_per_cycle": MAX_INSTANCES_PER_CYCLE,
            "websocket_streams": WEBSOCKET_STREAMS,
        }
        self.trade_action_min_interval_s = TRADE_ACTION_MIN_INTERVAL_S
        self.max_repeated_auto_actions = MAX_REPEATED_AUTO_ACTIONS
        self._last_trade_action_ts: Dict[str, float] = {}
        self._repeated_auto_actions: Dict[str, int] = {}
        self._module_backoff: Dict[str, Dict[str, float]] = {
            "sentiment": {"failures": 0.0, "next_retry_ts": 0.0},
            "xgboost": {"failures": 0.0, "next_retry_ts": 0.0},
            "onchain": {"failures": 0.0, "next_retry_ts": 0.0},
        }
        self._pair_risk_state: Dict[str, Dict[str, float]] = {}
        self.hardening_flags = {
            "safe_mode": _env_bool("AUTOBOT_SAFE_MODE", True),
            "enable_mean_reversion": _env_bool("ENABLE_MEAN_REVERSION", False),
            "enable_sentiment": _env_bool("ENABLE_SENTIMENT", False),
            "enable_ml": _env_bool("ENABLE_ML", False),
            "enable_trading_health_score": _env_bool("ENABLE_TRADING_HEALTH_SCORE", False),
            "enable_shadow_promotion": _env_bool("ENABLE_SHADOW_PROMOTION", True),
            "enable_rebalance": _env_bool("ENABLE_REBALANCE", True),
            "enable_auto_evolution": _env_bool("ENABLE_AUTO_EVOLUTION", True),
            "log_conflicts": _env_bool("ENABLE_CONFLICT_LOGGING", True),
        }
        self._config_validation_notes: List[str] = []

        # Validator
        self.validator = ValidatorEngine()

        # Instances
        self._instances: Dict[str, TradingInstanceAsync] = {}
        # ARCH-01: protect _instances dict mutations across concurrent coroutines
        self._instances_lock = asyncio.Lock()
        # Instance "racine" (parent) à préserver
        self.parent_instance_id: Optional[str] = None
        # Lien parent -> enfants (pour limiter les spin-offs en cascade)
        self._parent_children: Dict[str, set[str]] = {}
        # Lien enfant -> parent
        self._child_parent: Dict[str, str] = {}

        # Reconciliation
        self.reconciliation_manager: Optional[ReconciliationManagerAsync] = None

        # Config
        self.config = {
            "max_instances": 2000,  # Target: 2000+ instances
            "spin_off_threshold": float(SPIN_OFF_THRESHOLD),
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
        self._reuse_module_manager_instances()
        self.shadow_manager = self._init_shadow_manager()
        self._rebalance_manager = self._init_rebalance_manager()
        self._auto_evolution_manager = self._init_auto_evolution_manager()
        if self.hardening_flags["safe_mode"]:
            # SAFE MODE: external/noisy modules off by default unless explicitly enabled
            self.hardening_flags["enable_mean_reversion"] = (
                self.hardening_flags["enable_mean_reversion"]
                and self.module_manager.config.get("mean_reversion", False)
            )
            self.hardening_flags["enable_sentiment"] = (
                self.hardening_flags["enable_sentiment"]
                and self.module_manager.config.get("sentiment_nlp", False)
            )
            self.hardening_flags["enable_ml"] = (
                self.hardening_flags["enable_ml"]
                and self.module_manager.config.get("xgboost_predictor", False)
            )
        logger.info("🛡️ Hardening flags: %s", self.hardening_flags)
        logger.info(
            "🤖 Autonomous mode=%s decision_policy=%s",
            self.autonomous_mode,
            self.decision_policy,
        )
        logger.info("⚙️ Runtime constraints=%s", self.runtime_constraints)
        self._validate_runtime_configuration()

        logger.info("🎛️ OrchestratorAsync initialisé (target: 2000+ instances)")

    def _reuse_module_manager_instances(self) -> None:
        """
        Reuse already-loaded ModuleManager instances to avoid redundant objects.
        Keeps backward compatibility with local defaults when a module is disabled.
        """
        mapping = {
            "strategy_ensemble": "strategy_ensemble",
            "momentum_scoring": "momentum",
            "xgboost_predictor": "xgboost",
            "sentiment_nlp": "sentiment",
            "heuristic_predictor": "heuristic_predictor",
            "onchain_data": "onchain_data",
        }
        reused = []
        for module_name, attr_name in mapping.items():
            mod = self.module_manager.get(module_name)
            if mod is not None:
                setattr(self, attr_name, mod)
                reused.append(module_name)
        if reused:
            logger.info("♻️ Reused ModuleManager instances: %s", ", ".join(reused))

    def _validate_runtime_configuration(self) -> None:
        """Validate and normalize env-driven runtime configuration values."""
        notes: List[str] = []
        max_cycle = int(self.runtime_constraints.get("max_instances_per_cycle", MAX_INSTANCES_PER_CYCLE))
        if max_cycle < 1:
            self.runtime_constraints["max_instances_per_cycle"] = 1
            notes.append("max_instances_per_cycle<1 => forced to 1")
        elif max_cycle > self.config["max_instances"]:
            self.runtime_constraints["max_instances_per_cycle"] = int(self.config["max_instances"])
            notes.append("max_instances_per_cycle capped to max_instances")

        if self.trade_action_min_interval_s < 0.1:
            self.trade_action_min_interval_s = 0.1
            notes.append("trade_action_min_interval_s raised to 0.1s")
        elif self.trade_action_min_interval_s > 30.0:
            self.trade_action_min_interval_s = 30.0
            notes.append("trade_action_min_interval_s capped to 30s")

        if self.max_repeated_auto_actions < 1:
            self.max_repeated_auto_actions = 1
            notes.append("max_repeated_auto_actions raised to 1")
        elif self.max_repeated_auto_actions > 20:
            self.max_repeated_auto_actions = 20
            notes.append("max_repeated_auto_actions capped to 20")

        # Ensure non-negative priorities
        for key, value in list(self.decision_policy.items()):
            if value < 0:
                self.decision_policy[key] = 0
                notes.append(f"{key} priority raised to 0")

        self._config_validation_notes = notes
        if notes:
            logger.warning("⚙️ Runtime config normalized: %s", "; ".join(notes))

    def _init_shadow_manager(self) -> Optional[ShadowTradingManager]:
        """Initialize or reuse shadow manager with strict paper safeguards."""
        manager = self.module_manager.get("shadow_trading")
        if manager and isinstance(manager, ShadowTradingManager):
            if not hasattr(manager, "update_prices"):
                async def _update_prices() -> None:
                    await self._shadow_update_prices()
                setattr(manager, "update_prices", _update_prices)
            logger.info("🕶️ ShadowTradingManager déjà initialisé via ModuleManager")
            return manager

        if not self.paper_mode:
            logger.warning("🕶️ ShadowTradingManager ignoré: PAPER_TRADING=false")
            return None

        shadow_capital = 250.0  # 25% de 1000€ max
        if shadow_capital > 1000.0:
            shadow_capital = 1000.0
        manager = ShadowTradingManager()
        setattr(manager, "_shadow_capital_pool", shadow_capital)
        if not hasattr(manager, "update_prices"):
            async def _update_prices() -> None:
                await self._shadow_update_prices()
            setattr(manager, "update_prices", _update_prices)
        logger.info(
            "🕶️ ShadowTradingManager initialisé (pool=%.2f€, limite totale=1000€)",
            shadow_capital,
        )
        return manager

    def _init_rebalance_manager(self) -> Optional[RebalanceManager]:
        manager = self.module_manager.get("rebalance_manager")
        if manager and isinstance(manager, RebalanceManager):
            return manager
        return RebalanceManager(self)

    def _init_auto_evolution_manager(self) -> Optional[AutoEvolutionManager]:
        manager = self.module_manager.get("auto_evolution")
        if manager and isinstance(manager, AutoEvolutionManager):
            return manager
        return AutoEvolutionManager(db_path=os.getenv("AUTOEVOLUTION_DB", "data/autoevolution.db"))

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
            if self.parent_instance_id is None:
                # Première instance créée = parent racine (à ne pas supprimer)
                self.parent_instance_id = instance_id
            # Protection TrailingStop dédiée par instance
            self.trailing_stops[instance_id] = TrailingStopATR(
                atr_multiplier=2.5,
                activation_profit=1.5,
            )
            self.pyramiding[instance_id] = PyramidingManager(
                max_adds=3,
                profit_threshold_pct=1.5,
            )
            # MeanReversion explicitement branchée (safe init + isolation)
            try:
                MeanReversionStrategy.PRODUCTION_READY = True
                self.mean_reversion[instance_id] = MeanReversionStrategy(
                    window=20,
                    deviation=2.0,
                )
            except Exception as exc:
                logger.warning("MeanReversion init failed for %s: %s", instance_id, exc)
            finally:
                MeanReversionStrategy.PRODUCTION_READY = False

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
        self._evolution_pf_baseline[instance_id] = float(
            getattr(instance, "get_profit_factor_days", lambda _d: 1.0)(30)
        )

        if self.shadow_manager and self.paper_mode:
            try:
                self.shadow_manager.register_instance(instance_id, "crypto")
                shadow_pool = float(getattr(self.shadow_manager, "_shadow_capital_pool", 0.0))
                status = self.shadow_manager.get_status()
                shadow_count = max(int(status.get("shadow_count", 0)), 1)
                per_instance_capital = min(shadow_pool / shadow_count, 250.0)
                self.shadow_manager._instances[instance_id].paper_capital = per_instance_capital
                logger.info(
                    "🕶️ Shadow instance enregistrée: %s (paper_capital=%.2f€)",
                    instance_id,
                    per_instance_capital,
                )
            except Exception as exc:
                logger.warning("Shadow registration failed (isolé): %s", exc)

        if self._on_instance_created:
            self._on_instance_created(instance)

        return instance

    async def remove_instance(self, instance_id: str) -> bool:
        # ARCH-01: protect dict mutation with lock
        async with self._instances_lock:
            if instance_id not in self._instances:
                return False
            if instance_id == self.parent_instance_id:
                logger.warning(
                    "⚠️ Suppression bloquée: instance parent %s protégée",
                    instance_id,
                )
                return False
            instance = self._instances.pop(instance_id)
            self.trailing_stops.pop(instance_id, None)
            self.pyramiding.pop(instance_id, None)
            self.mean_reversion.pop(instance_id, None)
            self._evolution_pf_baseline.pop(instance_id, None)
            self._multi_grid.pop(instance_id, None)
            parent_id = self._child_parent.pop(instance_id, None)
            if parent_id:
                children = self._parent_children.get(parent_id)
                if children:
                    children.discard(instance_id)
            for symbol, owner_id in list(self._multi_grid_symbol_owner.items()):
                if owner_id == instance_id:
                    self._multi_grid_symbol_owner.pop(symbol, None)

        # P3: Unsubscribe from AsyncDispatcher (cancels queue, not ring reader
        # unless last subscriber for that pair)
        self.async_dispatcher.unsubscribe(instance_id)

        # instance.stop() drains the queue and cancels the consumer task
        await instance.stop()
        logger.info(f"🗑️ Instance supprimée: {instance_id}")
        return True

    async def create_instance_auto(
        self,
        parent_instance_id: Optional[str] = None,
        initial_capital: float = 0.0,
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
            initial_capital=initial_capital,
            leverage=1,
            grid_config={"range_percent": 7.0, "num_levels": 15},
        )
        return await self.create_instance(config)

    # ------------------------------------------------------------------
    # Spin-off & leverage
    # ------------------------------------------------------------------

    async def check_spin_off(self, parent: TradingInstanceAsync) -> Optional[TradingInstanceAsync]:
        capital = parent.get_current_capital()
        pf_30d = parent.get_profit_factor_days(30)
        # Une seule instance enfant active max par parent
        current_children = self._parent_children.get(parent.id, set())
        has_active_child = any(
            child_id in self._instances and self._instances[child_id].is_running()
            for child_id in current_children
        )
        if has_active_child:
            logger.debug("⏳ Spin-off bloqué: %s a déjà un enfant actif", parent.id)
            return None

        # Gate P0: PF minimum
        min_pf_for_spinoff = MIN_PF_FOR_SPINOFF
        if pf_30d < min_pf_for_spinoff:
            logger.info(
                "⏳ Spin-off bloqué pour %s: PF30 %.2f < %.2f",
                parent.id,
                pf_30d,
                min_pf_for_spinoff,
            )
            return None

        spin_off_ratio = 0.25
        min_child_capital = 400.0
        child_capital = int(capital * spin_off_ratio)
        if child_capital < min_child_capital:
            logger.info(
                "⏳ Spin-off bloqué pour %s: capital enfant %.2f€ < %.2f€",
                parent.id,
                child_capital,
                min_child_capital,
            )
            return None
        parent_available = parent.get_available_capital()
        if child_capital > parent_available:
            logger.info(
                "⏳ Spin-off bloqué pour %s: disponible %.2f€ < enfant %.2f€",
                parent.id,
                parent_available,
                float(child_capital),
            )
            return None

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
            new = await self.create_instance_auto(
                parent_instance_id=parent.id,
                initial_capital=float(child_capital),
            )
            if new:
                parent.record_spin_off(float(child_capital))
                self._child_parent[new.id] = parent.id
                self._parent_children.setdefault(parent.id, set()).add(new.id)
                self._activate_multi_grid_if_child(new)
                logger.info(
                    "🔄 Spin-off: %s → %s (parent: %.2f€ / child: %.2f€)",
                    parent.id,
                    new.id,
                    parent.get_current_capital(),
                    float(child_capital),
                )
                if self._on_instance_spinoff:
                    self._on_instance_spinoff(parent, new)
                return new
        return None

    def _activate_multi_grid_if_child(self, instance: TradingInstanceAsync) -> None:
        """Activate multi-grid only on child instances and coordinate symbol ownership."""
        parent_id = self._child_parent.get(instance.id)
        if not parent_id:
            logger.debug("MultiGrid ignoré pour parent/racine: %s", instance.id)
            return
        cfg = getattr(instance, "config", None)
        symbol = getattr(cfg, "symbol", None)
        if not symbol:
            logger.debug("MultiGrid ignoré: symbole indisponible pour %s", instance.id)
            return
        owner = self._multi_grid_symbol_owner.get(symbol)
        if owner and owner != instance.id:
            logger.info(
                "MultiGrid conflit évité: %s déjà géré par %s (skip %s)",
                symbol,
                owner,
                instance.id,
            )
            return
        profile = self._pair_registry.get(symbol)
        self._multi_grid[instance.id] = MultiGridOrchestrator(profile)
        self._multi_grid_symbol_owner[symbol] = instance.id
        logger.info("🧩 MultiGrid activé pour child=%s symbol=%s", instance.id, symbol)

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
                instances = self._select_instances_for_cycle()
                for inst in instances:
                    if not inst.is_running():
                        continue
                    await self._process_price_update(inst)

                await self._check_global_health()
                await asyncio.sleep(self.config["check_interval"] * 60)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"❌ Erreur main loop: {exc}")
                await asyncio.sleep(60)

    def _select_instances_for_cycle(self) -> List[TradingInstanceAsync]:
        """
        Select instances to process this cycle with lightweight portfolio ordering.
        Priority: higher PF30, then lower drawdown.
        """
        instances = [inst for inst in self._instances.values() if inst.is_running()]
        ranked = sorted(
            instances,
            key=lambda inst: (
                float(getattr(inst, "get_profit_factor_days", lambda _d: 1.0)(30)),
                -float(inst.get_drawdown()),
            ),
            reverse=True,
        )
        max_cycle = max(1, int(self.runtime_constraints["max_instances_per_cycle"]))
        if len(ranked) > max_cycle:
            logger.info(
                "⏱️ Cycle throttle: %d/%d instances traitées (CX33 guard)",
                max_cycle,
                len(ranked),
            )
        return ranked[:max_cycle]

    async def _process_price_update(self, inst: TradingInstanceAsync) -> None:
        """
        Process one instance cycle with explicit priority order (Decision Bus lite):
        1) Risk block (black swan / critical drawdown)
        2) Exit actions (trailing stop)
        3) Entry / add actions
        """
        t0 = perf_counter()
        if not self.autonomous_mode:
            logger.info("🤖 AUTOBOT_AUTONOMOUS=false -> cycle ignoré pour %s", inst.id)
            self._loop_metrics["process_cycle_ms"] = (perf_counter() - t0) * 1000.0
            return
        self._update_pair_risk_state(inst)

        risk_blocked = await self._run_black_swan_guard(inst)
        if risk_blocked:
            self._decision_stats["risk_blocks"] += 1
            self._set_last_decision(
                inst.id,
                action="RISK_BLOCK",
                reason="black_swan_guard",
            )
            self._loop_metrics["process_cycle_ms"] = (perf_counter() - t0) * 1000.0
            return

        exits_count = await self._check_exit_conditions(inst)
        if exits_count > 0:
            self._decision_stats["exit_actions"] += exits_count
            # Priorité aux sorties: on skip les entrées/adds sur ce cycle
            self._decision_stats["conflicts_resolved"] += 1
            self._set_last_decision(
                inst.id,
                action="EXIT",
                reason=f"trailing_stop_closed={exits_count}",
            )
            logger.info(
                "🧭 DecisionBus: exit-priority appliquée pour %s (%d fermeture(s))",
                inst.id,
                exits_count,
            )
            self._loop_metrics["process_cycle_ms"] = (perf_counter() - t0) * 1000.0
            return

        sig_t0 = perf_counter()
        opened = await self._evaluate_signal(inst)
        if opened:
            self._decision_stats["entry_actions"] += 1
            self._set_last_decision(
                inst.id,
                action="ENTRY",
                reason="ensemble_buy_open",
            )
        self._loop_metrics["signal_eval_ms"] = (perf_counter() - sig_t0) * 1000.0
        await self.check_spin_off(inst)
        if inst.config.leverage == 1:
            self.check_leverage_activation(inst)
        add_count = await self._evaluate_add_position(inst)
        if add_count > 0:
            self._decision_stats["add_actions"] += add_count
            self._set_last_decision(
                inst.id,
                action="ADD",
                reason=f"pyramiding_adds={add_count}",
            )
        if self.shadow_manager and self.paper_mode:
            try:
                sh_t0 = perf_counter()
                await self.shadow_manager.update_prices()
                self._loop_metrics["shadow_update_ms"] = (perf_counter() - sh_t0) * 1000.0
            except Exception as exc:
                logger.warning("Shadow update_prices erreur (isolée): %s", exc)
        if inst.get_drawdown() > self.config["max_drawdown_global"]:
            logger.error(f"🚨 Drawdown critique: {inst.id}")
            await inst.emergency_stop()
            if self._on_alert:
                self._on_alert("CRITICAL_DRAWDOWN", inst)
        self._loop_metrics["process_cycle_ms"] = (perf_counter() - t0) * 1000.0

    def _set_last_decision(self, instance_id: str, action: str, reason: str) -> None:
        priority = self.decision_policy.get(action, 0)
        self._last_decision = {
            "instance_id": instance_id,
            "action": action,
            "priority": priority,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _can_emit_trade_action(self, instance_id: str) -> bool:
        last_ts = self._last_trade_action_ts.get(instance_id)
        now = perf_counter()
        if last_ts is None:
            return True
        return (now - last_ts) >= self.trade_action_min_interval_s

    def _mark_trade_action(self, instance_id: str) -> None:
        self._last_trade_action_ts[instance_id] = perf_counter()

    def _module_can_run(self, name: str) -> bool:
        info = self._module_backoff.get(name)
        if not info:
            return True
        return perf_counter() >= float(info.get("next_retry_ts", 0.0))

    def _module_record_success(self, name: str) -> None:
        if name not in self._module_backoff:
            return
        self._module_backoff[name]["failures"] = 0.0
        self._module_backoff[name]["next_retry_ts"] = 0.0

    def _module_record_failure(self, name: str) -> None:
        """
        Exponential backoff for unstable modules:
        1s, 2s, 4s ... capped at MAX_BACKOFF_SECONDS.
        """
        if name not in self._module_backoff:
            return
        failures = float(self._module_backoff[name].get("failures", 0.0)) + 1.0
        delay = min(2 ** min(int(failures), 8), MAX_BACKOFF_SECONDS)
        self._module_backoff[name]["failures"] = failures
        self._module_backoff[name]["next_retry_ts"] = perf_counter() + delay

    def _update_pair_risk_state(self, instance: TradingInstanceAsync) -> None:
        """
        Maintain lightweight EMA state per symbol to calibrate risk by pair.
        """
        symbol = str(getattr(instance.config, "symbol", "UNKNOWN"))
        pf = float(instance.get_profit_factor_days(30))
        dd = float(instance.get_drawdown())
        state = self._pair_risk_state.setdefault(
            symbol,
            {"pf_ema": pf, "dd_ema": dd},
        )
        alpha = 0.2
        state["pf_ema"] = (alpha * pf) + ((1 - alpha) * float(state["pf_ema"]))
        state["dd_ema"] = (alpha * dd) + ((1 - alpha) * float(state["dd_ema"]))

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
        if self.hardening_flags.get("enable_trading_health_score", False):
            health = self._compute_health_score()
            if health < HEALTH_SCORE_THRESHOLD:
                logger.warning("🩺 Trading health score faible: %.1f/100", health)
                if self._on_alert:
                    self._on_alert("LOW_HEALTH_SCORE", {"score": health})

    async def _run_black_swan_guard(self, instance: TradingInstanceAsync) -> bool:
        """
        Détection Black Swan avant autres traitements.
        """
        try:
            last_price = instance.get_status().get("last_price")
            if not last_price or last_price <= 0:
                return False
            event = self.black_swan.on_price(price=float(last_price), volume=0.0)
            if event:
                logger.critical(
                    "🦢 Black Swan détecté (%s) sur %s — emergency close all",
                    event.get("type", "unknown"),
                    instance.id,
                )
                await self._emergency_close_all()
                return True
        except Exception as exc:
            logger.warning("Black Swan guard erreur (isolée): %s", exc)
        return False

    def _map_regime(self, trend: str) -> MarketRegime:
        if trend == "range":
            return MarketRegime.RANGE
        if trend in ("up", "down"):
            return MarketRegime.TREND_FORTE
        return MarketRegime.TREND_FAIBLE

    async def _evaluate_signal(self, instance: TradingInstanceAsync) -> bool:
        """
        Combine grid + mean reversion via StrategyEnsemble.
        MeanReversion activée uniquement en régime range-bound.
        """
        try:
            status = instance.get_status()
            price = status.get("last_price")
            if not price or price <= 0:
                return False
            price = float(price)
            trend = instance.detect_trend()
            regime = self._map_regime(trend)
            volume = 0.0
            positions = instance.get_positions_snapshot()
            if positions:
                volume = sum(float(p.get("volume") or 0.0) for p in positions)

            # Signal grid (proxy léger sans modifier la logique grid existante)
            grid_signal = "BUY" if trend == "range" else "HOLD"
            grid_score = 0.6

            # MeanReversion : activée uniquement en range
            mr_signal = "HOLD"
            mr = self.mean_reversion.get(instance.id)
            if self.hardening_flags["enable_mean_reversion"] and mr and trend == "range":
                mr.update(price)
                mr_signal = "BUY" if mr.should_enter() else "HOLD"
            logger.info("MeanReversion signal: %s", mr_signal)

            # Sentiment update/read (timeout strict 5s)
            sentiment_score = 0.0
            if self.hardening_flags["enable_sentiment"] and self._module_can_run("sentiment"):
                try:
                    loop = asyncio.get_running_loop()
                    await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: self.sentiment.add_text(
                                f"{instance.config.symbol} price={price:.2f} trend={trend}",
                                source="internal",
                            ),
                        ),
                        timeout=5.0,
                    )
                    sentiment = await asyncio.wait_for(
                        loop.run_in_executor(None, self.sentiment.get_aggregate_sentiment),
                        timeout=5.0,
                    )
                    sentiment_score = float(sentiment.get("score", 0.0))
                    logger.info("Sentiment: %.3f", sentiment_score)
                    self._module_record_success("sentiment")
                except Exception as exc:
                    logger.warning("Sentiment unavailable (isolé): %s", exc)
                    self._module_record_failure("sentiment")

            # On-chain feature (best effort)
            if self._module_can_run("onchain"):
                try:
                    self.onchain_data.update_metrics()
                    onchain_signal = self.onchain_data.get_signal()
                    onchain_score = float(onchain_signal.get("score", 0.0))
                    self._module_record_success("onchain")
                except Exception:
                    onchain_score = 0.0
                    self._module_record_failure("onchain")
            else:
                onchain_score = 0.0

            # ML prediction: XGBoost puis fallback Heuristic
            ml_confidence = 0.0
            ml_direction = "HOLD"
            if self.hardening_flags["enable_ml"] and self._module_can_run("xgboost"):
                try:
                    features = self.xgboost.extract_features(price=price, volume=volume)
                    if features is not None:
                        features_ext = list(features) + [onchain_score]
                        prediction = self.xgboost.predict(features_ext)
                        if prediction is not None:
                            ml_confidence = float(prediction.get("probability", 0.0))
                            ml_direction = "BUY" if prediction.get("direction") == "UP" else "SELL"
                        else:
                            self.heuristic_predictor.update(price=price, volume=volume)
                            hp = self.heuristic_predictor.predict()
                            if hp is not None:
                                ml_confidence = float(hp.confidence)
                                ml_direction = "BUY" if hp.probability_up >= 0.5 else "SELL"

                        # enrichit dataset XGBoost (label naïf basée sur tendance)
                        label = 1 if trend == "up" else 0
                        self.xgboost.add_sample(features_ext, label)
                    self._module_record_success("xgboost")
                except Exception as exc:
                    logger.warning("ML path unavailable (isolé): %s", exc)
                    self._module_record_failure("xgboost")

            logger.info("ML prediction: %s (confidence %.3f)", ml_direction, ml_confidence)

            # Ajustement léger des poids selon momentum + sentiment + ML
            momentum_score = float(self.momentum.on_price(price))
            if momentum_score > 70 or sentiment_score > 0.2:
                grid_score += 0.1
            elif momentum_score < 30 or sentiment_score < -0.2:
                grid_score -= 0.1
            if ml_confidence > 0.7 and ml_direction == "BUY":
                grid_score += 0.1
            grid_score = min(max(grid_score, 0.1), 0.9)
            mr_score = max(0.1, 1.0 - grid_score)

            self.strategy_ensemble.update_signal("grid", grid_signal, grid_score)
            self.strategy_ensemble.update_signal("mean_reversion", mr_signal, mr_score)

            ensemble = self.strategy_ensemble.get_signal(regime)
            consensus = float(ensemble.score)
            if (
                self.hardening_flags["log_conflicts"]
                and grid_signal != mr_signal
                and grid_signal != "HOLD"
                and mr_signal != "HOLD"
            ):
                logger.warning(
                    "⚔️ Conflit signaux: grid=%s vs mean_reversion=%s — décision ensemble=%s (%.3f)",
                    grid_signal,
                    mr_signal,
                    ensemble.direction,
                    consensus,
                )

            logger.info("Ensemble consensus: %.3f", consensus)
            if consensus < 0.5:
                return False

            final_direction = ensemble.direction
            if final_direction != "BUY":
                return False

            # Évite conflit: n'ouvre que s'il n'y a aucune position open
            open_positions = [p for p in instance.get_positions_snapshot() if p.get("status") == "open"]
            if open_positions:
                return False
            repeated_actions = self._repeated_auto_actions.get(instance.id, 0)
            if repeated_actions >= self.max_repeated_auto_actions:
                logger.warning(
                    "⛔ Repeated auto-action limit hit: inst=%s count=%d",
                    instance.id,
                    repeated_actions,
                )
                return False
            if not self._can_emit_trade_action(instance.id):
                logger.info(
                    "⏱️ Trade action throttled for %s (min interval %.2fs)",
                    instance.id,
                    self.trade_action_min_interval_s,
                )
                return False

            base_size = max(instance.get_current_capital() * 0.02, 1.0)
            sized = self._calculate_position_size(
                instance=instance,
                base_size_eur=base_size,
                current_volatility=max(instance.get_volatility(), 1e-8),
            )
            volume = sized / price
            if volume <= 0:
                return False
            await instance.open_position(price=price, volume=volume)
            self._mark_trade_action(instance.id)
            self._repeated_auto_actions[instance.id] = repeated_actions + 1
            return True
        except Exception as exc:
            logger.warning("Signal evaluation erreur (isolée): %s", exc)
        return False

    async def _train_xgboost_loop(self) -> None:
        """
        Boucle d'entraînement périodique XGBoost (toutes les 24h, hors lock principal).
        """
        while self.running:
            try:
                await asyncio.sleep(24 * 3600)
                if not self.hardening_flags["enable_ml"]:
                    continue
                if not self._module_can_run("xgboost"):
                    continue
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self.xgboost._train)
                self._module_record_success("xgboost")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("XGBoost training loop erreur (isolée): %s", exc)
                self._module_record_failure("xgboost")

    async def _sentiment_update_loop(self) -> None:
        """
        Boucle de rafraîchissement sentiment (toutes les 1h).
        """
        while self.running:
            try:
                await asyncio.sleep(3600)
                if not self.hardening_flags["enable_sentiment"]:
                    continue
                if not self._module_can_run("sentiment"):
                    continue
                loop = asyncio.get_running_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: self.sentiment.add_text(
                            "market update heartbeat",
                            source="system",
                        ),
                    ),
                    timeout=5.0,
                )
                self._module_record_success("sentiment")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Sentiment loop erreur (isolée): %s", exc)
                self._module_record_failure("sentiment")

    async def _shadow_update_prices(self) -> None:
        """Best-effort shadow metrics refresh (called from processing cycle)."""
        if not self.shadow_manager:
            return
        for inst in list(self._instances.values()):
            if not inst.is_running():
                continue
            try:
                pf = float(inst.get_profit_factor_days(30))
                trades = int(len(getattr(inst, "_trades", [])))
                self.shadow_manager.update_performance(inst.id, pf=pf, trades=trades)
            except Exception as exc:
                logger.warning("Shadow metrics refresh failed for %s: %s", inst.id, exc)

    async def _check_shadow_promotions(self) -> None:
        """Check every hour if shadow PF > 1.5 and promote with 25% transfer."""
        while self.running:
            try:
                await asyncio.sleep(3600)
                if not self.paper_mode or not self.shadow_manager:
                    continue
                if not self.hardening_flags["enable_shadow_promotion"]:
                    continue
                status = self.shadow_manager.get_status()
                instances = status.get("instances", {})
                for inst_id, meta in instances.items():
                    pf = float(meta.get("pf", 0.0))
                    if pf <= 1.5:
                        continue
                    if not self.shadow_manager.should_promote_to_live(inst_id):
                        continue
                    paper_capital = float(meta.get("paper_capital", 0.0))
                    transfer_amount = paper_capital * 0.25 if paper_capital > 0 else 0.0
                    if transfer_amount <= 0:
                        continue
                    async with self._capital_ops_lock:
                        ok = self.shadow_manager.transfer_capital(inst_id, transfer_amount)
                    if ok:
                        logger.info(
                            "🟢 Promotion shadow→live: %s PF=%.2f transfert=%.2f€ (25%% shadow)",
                            inst_id,
                            pf,
                            transfer_amount,
                        )
                    else:
                        logger.warning(
                            "Promotion shadow refusée: %s PF=%.2f transfert=%.2f€",
                            inst_id,
                            pf,
                            transfer_amount,
                        )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Shadow promotion loop erreur (isolée): %s", exc)

    async def _rebalance_loop(self) -> None:
        """Run rebalance checks every 7 days with 10% max transfer rule."""
        while self.running:
            try:
                await asyncio.sleep(7 * 24 * 3600)
                if not self.hardening_flags["enable_rebalance"]:
                    continue
                active = [inst for inst in self._instances.values() if inst.is_running()]
                if len(active) < 2:
                    logger.info("⚖️ Rebalance skip: moins de 2 instances actives")
                    continue
                if not self._rebalance_manager:
                    continue
                async with self._capital_ops_lock:
                    events = await self._rebalance_manager.check_and_rebalance()
                for event in events:
                    max_allowed = event.capital_before * 0.10
                    if event.amount > max_allowed:
                        logger.warning(
                            "⚖️ Rebalance capped: %s demandé %.2f€ > max 10%% %.2f€",
                            event.instance_id,
                            event.amount,
                            max_allowed,
                        )
                    logger.info(
                        "⚖️ Rebalance action=%s instance=%s amount=%.2f€ reason=%s",
                        event.action,
                        event.instance_id,
                        min(event.amount, max_allowed),
                        event.reason,
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Rebalance loop erreur (isolée): %s", exc)

    async def _auto_evolution_loop(self) -> None:
        """Evaluate parameter evolution every 2 weeks with PF rollback check."""
        while self.running:
            try:
                await asyncio.sleep(14 * 24 * 3600)
                if not self.hardening_flags["enable_auto_evolution"]:
                    continue
                if not self._auto_evolution_manager:
                    continue
                for inst in list(self._instances.values()):
                    if not inst.is_running():
                        continue
                    pf_now = float(inst.get_profit_factor_days(30))
                    baseline = self._evolution_pf_baseline.get(inst.id, pf_now)
                    eligibility = self._auto_evolution_manager.evaluate_transition_eligibility(
                        current_capital=float(inst.get_current_capital()),
                        initial_capital=float(inst.get_initial_capital()),
                        max_drawdown_pct=-float(inst.get_drawdown() * 100.0),
                        atr_14=max(float(inst.get_volatility() * 100.0), 0.01),
                        max_1h_spike=0.0,
                    )
                    logger.info(
                        "🧬 AutoEvolution check: inst=%s eligible=%s PF=%.2f baseline=%.2f",
                        inst.id,
                        bool(eligibility.get("eligible")),
                        pf_now,
                        baseline,
                    )
                    if eligibility.get("eligible"):
                        logger.info("🧪 Evolution test en shadow pour %s", inst.id)
                    if pf_now < baseline:
                        rollback = self._auto_evolution_manager.request_downgrade_to_phase_1(
                            reason=f"PF drop {pf_now:.2f} < baseline {baseline:.2f}"
                        )
                        logger.warning("↩️ AutoEvolution rollback: %s", rollback)
                    else:
                        self._evolution_pf_baseline[inst.id] = pf_now
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("AutoEvolution loop erreur (isolée): %s", exc)

    async def _check_exit_conditions(self, instance: TradingInstanceAsync) -> int:
        """
        Vérifie trailing stop sur positions ouvertes.
        N'altère pas la logique métier existante; ajoute uniquement une protection.
        """
        try:
            closed_count = 0
            trailing = self.trailing_stops.get(instance.id)
            if not trailing:
                return 0
            status = instance.get_status()
            current_price = status.get("last_price")
            if not current_price or current_price <= 0:
                return 0

            # ATR indisponible dans ce contexte -> approximation conservatrice 1% du prix
            atr = max(float(current_price) * 0.01, 1e-8)

            for pos in instance.get_positions_snapshot():
                if pos.get("status") != "open":
                    continue
                entry_price = float(pos.get("entry_price") or 0.0)
                if entry_price <= 0:
                    continue
                profit_pct = ((float(current_price) - entry_price) / entry_price) * 100.0
                if profit_pct <= 1.5:
                    continue

                stop_price = trailing.update(
                    price=float(current_price),
                    atr=atr,
                    entry_price=entry_price,
                )
                if float(current_price) <= stop_price:
                    logger.warning(
                        "🛡️ Trailing stop hit: inst=%s pos=%s price=%.4f stop=%.4f",
                        instance.id,
                        pos.get("id"),
                        float(current_price),
                        float(stop_price),
                    )
                    await instance.close_position(str(pos.get("id")), float(current_price))
                    closed_count += 1
                    self._repeated_auto_actions[instance.id] = 0
        except Exception as exc:
            logger.warning("Trailing stop check erreur (isolée): %s", exc)
            return 0
        return closed_count

    def _calculate_position_size(
        self,
        instance: TradingInstanceAsync,
        base_size_eur: float,
        current_volatility: float,
    ) -> float:
        """
        Sizing unifié (volatilité + Kelly) avec fallback conservateur.
        """
        try:
            capital = max(instance.get_current_capital(), 0.0)
            if capital <= 0:
                return 0.0

            # 1) Ajustement volatilité (target 2%)
            target_volatility = TARGET_VOLATILITY
            vol_adj = 1.0
            if current_volatility > 0:
                vol_adj = min(max(target_volatility / current_volatility, 0.5), 2.0)
            logger.info(
                "Position size adjusted by volatility: %.2f%%",
                vol_adj * 100.0,
            )
            vol_sized = base_size_eur * vol_adj

            # 2) Kelly half with cap 25%
            trades = list(getattr(instance, "_trades", []))
            wins = [t for t in trades if (t.profit or 0.0) > 0]
            losses = [t for t in trades if (t.profit or 0.0) < 0]
            total = len(trades)
            win_rate = (len(wins) / total) if total > 0 else 0.5
            avg_win = (sum((t.profit or 0.0) for t in wins) / len(wins)) if wins else 1.0
            avg_loss = (abs(sum((t.profit or 0.0) for t in losses)) / len(losses)) if losses else 1.0
            pf_30d = instance.get_profit_factor_days(30)
            kelly_size = self.kelly_criterion.calculate_position_size(
                win_rate=win_rate,
                avg_win=float(max(avg_win, 1e-8)),
                avg_loss=float(max(avg_loss, 1e-8)),
                current_capital=capital,
                current_pf=float(pf_30d if pf_30d != float("inf") else 2.0),
            )
            # Si Kelly trop conservateur (ex: historique insuffisant), fallback vers vol_sized.
            combined = kelly_size if kelly_size > 0 else vol_sized

            # 3) Bornes 1%-5% du capital
            min_size = capital * 0.01
            max_size = capital * 0.05
            final_size = max(min(combined, max_size), min_size)
            risk_multiplier = self._compute_risk_multiplier(instance)
            final_size *= risk_multiplier
            logger.info("Risk multiplier applied: %.2f", risk_multiplier)
            return float(final_size)
        except Exception as exc:
            logger.warning("Sizing avancé indisponible, fallback ancien calcul: %s", exc)
            # Fallback ancien calcul (inchangé)
            return float(base_size_eur)

    def _compute_risk_multiplier(self, instance: TradingInstanceAsync) -> float:
        """
        Portfolio-level autonomous risk scaling.
        Objective: preserve PF by reducing risk in degradation phases.
        """
        try:
            pf_30 = float(instance.get_profit_factor_days(30))
            drawdown = float(instance.get_drawdown())
            symbol = str(getattr(instance.config, "symbol", "UNKNOWN"))
            pair_state = self._pair_risk_state.get(symbol, {})
            pair_pf = float(pair_state.get("pf_ema", pf_30))
            pair_dd = float(pair_state.get("dd_ema", drawdown))
            multiplier = 1.0
            if pf_30 < 1.2:
                multiplier *= 0.5
            elif pf_30 < 1.6:
                multiplier *= 0.75
            elif pf_30 > 2.5:
                multiplier *= 1.10

            if drawdown > 0.20:
                multiplier *= 0.5
            elif drawdown > 0.10:
                multiplier *= 0.75
            # Pair-level calibration (EMA-based) to avoid over-sizing weak symbols
            if pair_pf < 1.2:
                multiplier *= 0.8
            elif pair_pf > 2.0 and pair_dd < 0.08:
                multiplier *= 1.05
            if pair_dd > 0.15:
                multiplier *= 0.8
            return min(max(multiplier, 0.25), 1.25)
        except Exception:
            return 1.0

    def _compute_health_score(self) -> float:
        """
        Lightweight runtime health score [0, 100] for observability/alerts.
        """
        score = 100.0
        try:
            if not self.ws_client.is_connected():
                score -= 30.0
            if self._module_backoff.get("sentiment", {}).get("failures", 0) > 3:
                score -= 10.0
            if self._module_backoff.get("xgboost", {}).get("failures", 0) > 3:
                score -= 10.0
            if self._module_backoff.get("onchain", {}).get("failures", 0) > 3:
                score -= 10.0

            critical_drawdowns = sum(
                1 for inst in self._instances.values()
                if inst.is_running() and float(inst.get_drawdown()) > self.config["max_drawdown_global"]
            )
            score -= min(critical_drawdowns * 5.0, 30.0)

            proc_ms = float(self._loop_metrics.get("process_cycle_ms", 0.0))
            if proc_ms > 5000:
                score -= 20.0
            elif proc_ms > 2000:
                score -= 10.0
        except Exception:
            score -= 20.0
        return max(0.0, min(100.0, score))

    async def _add_to_position(
        self,
        instance: TradingInstanceAsync,
        position_id: str,
        size_eur: float,
    ) -> None:
        """
        Ajoute une sous-position (approche additive) en réutilisant open_position.
        """
        try:
            status = instance.get_status()
            current_price = status.get("last_price")
            if not current_price or current_price <= 0 or size_eur <= 0:
                return
            if not self._can_emit_trade_action(instance.id):
                logger.info(
                    "⏱️ Add action throttled for %s (min interval %.2fs)",
                    instance.id,
                    self.trade_action_min_interval_s,
                )
                return
            volume = float(size_eur) / float(current_price)
            if volume <= 0:
                return
            opened = await instance.open_position(
                price=float(current_price),
                volume=volume,
            )
            if opened:
                self._mark_trade_action(instance.id)
                self._repeated_auto_actions[instance.id] = self._repeated_auto_actions.get(instance.id, 0) + 1
                logger.info(
                    "📈 Pyramiding add: inst=%s base_pos=%s add=%.2f€ vol=%.6f",
                    instance.id,
                    position_id,
                    float(size_eur),
                    volume,
                )
        except Exception as exc:
            logger.warning("Pyramiding add erreur (isolée): %s", exc)

    async def _evaluate_add_position(self, instance: TradingInstanceAsync) -> int:
        """
        Évalue les ajouts pyramiding sur positions gagnantes.
        """
        try:
            adds_done = 0
            manager = self.pyramiding.get(instance.id)
            if not manager:
                return 0
            status = instance.get_status()
            current_price = status.get("last_price")
            if not current_price or current_price <= 0:
                return
            current_price = float(current_price)

            for pos in instance.get_positions_snapshot():
                if pos.get("status") != "open":
                    continue
                entry_price = float(pos.get("entry_price") or 0.0)
                volume = float(pos.get("volume") or 0.0)
                if entry_price <= 0 or volume <= 0:
                    continue

                # initialise contexte pyramiding à la première observation
                if not manager.get_status().get("is_open"):
                    manager.open_position(entry_price=entry_price, base_size=volume)

                profit_pct = ((current_price - entry_price) / entry_price) * 100.0
                pyramiding_level = int(manager.get_status().get("current_level", 0))
                if profit_pct <= 1.5 or pyramiding_level >= 3:
                    continue

                add_decision = manager.add_to_position(current_price)
                if not add_decision:
                    continue

                # base demandé: 50% de la position actuelle
                base_add_size_eur = (volume * entry_price) * 0.5
                current_volatility = max(instance.get_volatility(), 1e-8)
                sized_add_eur = self._calculate_position_size(
                    instance=instance,
                    base_size_eur=base_add_size_eur,
                    current_volatility=current_volatility,
                )
                await self._add_to_position(
                    instance=instance,
                    position_id=str(pos.get("id")),
                    size_eur=sized_add_eur,
                )
                adds_done += 1
        except Exception as exc:
            logger.warning("Pyramiding evaluation erreur (isolée): %s", exc)
            return 0
        return adds_done

    async def _emergency_close_all(self) -> None:
        """Alias explicite pour fermer toutes les positions/instances en urgence."""
        await self.emergency_stop_all()

    async def _daily_report_loop(self) -> None:
        """
        Génère un rapport quotidien à minuit UTC.
        """
        while self.running:
            try:
                now = datetime.now(timezone.utc)
                next_day = (now + timedelta(days=1)).replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                wait_seconds = max((next_day - now).total_seconds(), 1.0)
                await asyncio.sleep(wait_seconds)
                try:
                    report = self.daily_reporter.generate_report()
                    logger.info(
                        "🗓️ Daily report généré: date=%s trades=%s",
                        report.get("date"),
                        report.get("total_trades"),
                    )
                except Exception as exc:
                    logger.warning("Daily report génération erreur (isolée): %s", exc)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Daily report loop erreur (isolée): %s", exc)
                await asyncio.sleep(60)

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
        self._daily_report_task = asyncio.create_task(self._daily_report_loop())
        self._xgboost_train_task = asyncio.create_task(self._train_xgboost_loop())
        self._sentiment_task = asyncio.create_task(self._sentiment_update_loop())
        if self.paper_mode:
            total_capital = sum(
                float(inst.get_current_capital()) for inst in self._instances.values()
            ) + float(getattr(self.shadow_manager, "_shadow_capital_pool", 0.0) if self.shadow_manager else 0.0)
            if total_capital > 1000.0:
                logger.warning(
                    "🕶️ Capital total paper+shadow %.2f€ > 1000€ (limite demandée)",
                    total_capital,
                )
            self._shadow_promotion_task = asyncio.create_task(self._check_shadow_promotions())
            self._rebalance_task = asyncio.create_task(self._rebalance_loop())
            self._auto_evolution_task = asyncio.create_task(self._auto_evolution_loop())
            logger.info("🧪 Advanced modules activés en PAPER_TRADING=true")
        else:
            logger.warning("🧪 Advanced modules désactivés (PAPER_TRADING=false)")

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
        if self._daily_report_task:
            self._daily_report_task.cancel()
            try:
                await self._daily_report_task
            except asyncio.CancelledError:
                pass
            self._daily_report_task = None
        if self._xgboost_train_task:
            self._xgboost_train_task.cancel()
            try:
                await self._xgboost_train_task
            except asyncio.CancelledError:
                pass
            self._xgboost_train_task = None
        if self._sentiment_task:
            self._sentiment_task.cancel()
            try:
                await self._sentiment_task
            except asyncio.CancelledError:
                pass
            self._sentiment_task = None
        if self._shadow_promotion_task:
            self._shadow_promotion_task.cancel()
            try:
                await self._shadow_promotion_task
            except asyncio.CancelledError:
                pass
            self._shadow_promotion_task = None
        if self._rebalance_task:
            self._rebalance_task.cancel()
            try:
                await self._rebalance_task
            except asyncio.CancelledError:
                pass
            self._rebalance_task = None
        if self._auto_evolution_task:
            self._auto_evolution_task.cancel()
            try:
                await self._auto_evolution_task
            except asyncio.CancelledError:
                pass
            self._auto_evolution_task = None

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
            "autonomous_mode": self.autonomous_mode,
            "runtime_constraints": dict(self.runtime_constraints),
            "config_validation_notes": list(self._config_validation_notes),
            "execution_throttle": {
                "trade_action_min_interval_s": self.trade_action_min_interval_s,
                "max_repeated_auto_actions": self.max_repeated_auto_actions,
            },
            "module_backoff": dict(self._module_backoff),
            "pair_risk_state": {
                k: v for k, v in list(self._pair_risk_state.items())[:20]
            },
            "hardening_flags": dict(self.hardening_flags),
            "decision_policy": dict(self.decision_policy),
            "loop_metrics_ms": dict(self._loop_metrics),
            "decision_stats": dict(self._decision_stats),
            "last_decision": dict(self._last_decision),
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
        if self.hardening_flags.get("enable_trading_health_score", False):
            status["trading_health_score"] = self._compute_health_score()
        return status

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
