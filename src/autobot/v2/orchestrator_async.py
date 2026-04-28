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
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, Coroutine, Dict, List, Optional

from .modules.order_flow_imbalance import OrderFlowImbalance
from .system_optimizer import SystemOptimizer
from .ring_buffer_dispatcher import RingBufferDispatcher
from .system_optimizer import SystemOptimizer
from .modules.order_flow_imbalance import OrderFlowImbalance
from .async_dispatcher import AsyncDispatcher
from .websocket_async import TickerData
from .instance_async import TradingInstanceAsync
from .order_executor_async import OrderExecutorAsync, get_order_executor_async
try:
    from .paper_trading import PaperTradingExecutor
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
from .modules.multi_indicator_vote import MultiIndicatorVoter
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
from .decision_engine import DecisionEngine
from .module_coordinator import ModuleCoordinator
from .robustness_guard import RobustnessGuard
from .regime_controller import RegimeController
from .risk_cluster_manager import RiskClusterManager
from .safety_guard import SafetyGuard
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
    SAFETY_DSR_TIMEOUT_MS,
    SAFETY_DSR_CACHE_S,
    SAFETY_WF_LEARNING_DAYS,
    SAFETY_WF_MIN_TRADES_LEARNING,
    SAFETY_MAX_BLOCK_RATIO,
    SAFETY_EMERGENCY_CYCLE_MS,
    SAFETY_EMERGENCY_CONSECUTIVE,
    ENABLE_UNIVERSE_MANAGER,
    UNIVERSE_ENABLE_FOREX,
    UNIVERSE_MAX_ELIGIBLE,
    UNIVERSE_MAX_SUPPORTED,
    ENABLE_PAIR_RANKING_ENGINE,
    RANKING_MIN_SCORE_ACTIVATE,
    RANKING_UPDATE_SECONDS,
    ENABLE_SCALABILITY_GUARD,
    SCALING_GUARD_CPU_PCT_MAX,
    SCALING_GUARD_MEMORY_PCT_MAX,
    SCALING_GUARD_WS_STALE_SECONDS_MAX,
    SCALING_GUARD_WS_LAG_MAX,
    SCALING_GUARD_EXEC_FAILURE_RATE_MAX,
    SCALING_GUARD_RECON_MISMATCH_MAX,
    SCALING_GUARD_PF_MIN,
    SCALING_GUARD_VALIDATION_FAIL_MAX,
    ENABLE_INSTANCE_ACTIVATION_MANAGER,
    ACTIVATION_DEFAULT_TIER,
    ACTIVATION_PROMOTE_SCORE_MIN,
    ACTIVATION_DEMOTE_SCORE_MAX,
    ACTIVATION_PROMOTE_HEALTH_MIN,
    ACTIVATION_DEMOTE_HEALTH_MAX,
    ACTIVATION_HYSTERESIS_CYCLES,
    ACTIVATION_COOLDOWN_SECONDS,
    ENABLE_PORTFOLIO_ALLOCATOR,
    PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO,
    PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO,
    PORTFOLIO_RESERVE_CASH_RATIO,
    PORTFOLIO_MAX_TOTAL_ACTIVE_RISK_RATIO,
    PORTFOLIO_RISK_PER_CAPITAL_RATIO,
    ENABLE_DECISION_JOURNAL,
    DECISION_JOURNAL_MAX_SYMBOLS,
)
from .risk_manager import OrchestratorRiskManager
from .universe_manager import UniverseManager
from .pair_ranking_engine import PairRankingEngine
from .scalability_guard import (
    GuardThresholds,
    ScalabilityGuard,
    ScalingState,
)
from .global_kill_switch import GlobalKillSwitchStore
from .instance_activation_manager import (
    InstanceActivationManager,
)
from .portfolio_allocator import (
    AllocationConstraints,
    AllocationPlan,
    PortfolioAllocator,
)
from .orchestrator_services import (
    ActivationContext,
    BackgroundTasksService,
    DecisionJournalService,
    InstanceActivationService,
    InstanceLifecycleService,
    PortfolioAllocationService,
    ReportingService,
    ScalabilityGuardService,
    ScalabilityMetrics,
    SafetyService,
    journal_symbol_cap,
)
from .decision_journal import (
    DecisionJournal,
    journal_from_env,
    REJECTION_REASON_ALLOCATION_ENVELOPE_BLOCKED,
    REJECTION_REASON_BLACK_SWAN_EMERGENCY_BLOCK,
    REJECTION_REASON_RANKING_BELOW_THRESHOLD,
    REJECTION_REASON_REPEATED_AUTO_ACTION_BLOCK,
    REJECTION_REASON_SCALABILITY_GUARD_BLOCK,
    REJECTION_REASON_SYMBOL_NOT_SELECTED,
    REJECTION_REASON_VALIDATION_GUARD_BLOCK,
)

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    return value in ("1", "true", "yes", "on")


def _apply_force_enable_all_hardening_flags(hardening_flags: Dict[str, bool]) -> None:
    if _env_bool("AUTOBOT_FORCE_ENABLE_ALL", False):
        for flag in (
            "enable_mean_reversion",
            "enable_sentiment",
            "enable_ml",
            "enable_xgboost",
            "enable_onchain",
            "enable_trading_health_score",
            "enable_shadow_promotion",
            "enable_shadow_trading",
            "enable_rebalance",
            "enable_auto_evolution",
            "enable_validation_guard",
        ):
            hardening_flags[flag] = True


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
        self.api_key = api_key # SEC-01: handled by __repr__
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
        self._last_capital_snapshot: Dict[str, Any] = {
            "paper_mode": self.paper_mode,
            "source": "paper" if self.paper_mode else "kraken",
            "source_status": "not_loaded",
        }

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
        self.voter = MultiIndicatorVoter(min_votes_required=2)
        self.sentiment = SentimentAnalyzer()
        self.heuristic_predictor = HeuristicPredictor()
        self.onchain_data = OnchainDataModule()
        self.voter.register_indicator("xgboost", weight=1.2)
        self.voter.register_indicator("heuristic", weight=1.0)
        self.voter.register_indicator("sentiment", weight=0.8)
        self.daily_reporter = DailyReporter(self)
        self._daily_report_task: Optional[asyncio.Task] = None
        self._xgboost_train_task: Optional[asyncio.Task] = None
        self._sentiment_task: Optional[asyncio.Task] = None
        self._shadow_promotion_task: Optional[asyncio.Task] = None
        self._rebalance_task: Optional[asyncio.Task] = None
        self._auto_evolution_task: Optional[asyncio.Task] = None
        self._cycle_health_task: Optional[asyncio.Task] = None
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
        self._instance_first_seen_ts: Dict[str, float] = {}
        self._wf_blocked_24h = 0
        self._wf_window_start = datetime.now(timezone.utc)
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
        self.decision_journal: DecisionJournal = journal_from_env()
        self._decision_journal_enabled = bool(ENABLE_DECISION_JOURNAL)
        self._journal_last_ranking_fp: Optional[str] = None
        self._journal_last_guard_state: str = ScalingState.ALLOW_SCALE_UP.value
        self._journal_last_guard_fp: Optional[str] = None
        self._journal_last_allocation_fp: Optional[str] = None
        self._journal_last_rejected_ranking_fp: Optional[str] = None
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
            "enable_mean_reversion": _env_bool("ENABLE_MEAN_REVERSION", True),
            "enable_sentiment": _env_bool("ENABLE_SENTIMENT", True),
            "enable_ml": _env_bool("ENABLE_ML", True),
            "enable_xgboost": _env_bool("ENABLE_XGBOOST", _env_bool("ENABLE_ML", True)),
            "enable_onchain": _env_bool("ENABLE_ONCHAIN", True),
            "enable_trading_health_score": _env_bool("ENABLE_TRADING_HEALTH_SCORE", True),
            "enable_shadow_promotion": _env_bool("ENABLE_SHADOW_PROMOTION", True),
            "enable_shadow_trading": _env_bool("ENABLE_SHADOW_TRADING", True),
            "enable_rebalance": _env_bool("ENABLE_REBALANCE", True),
            "enable_auto_evolution": _env_bool("ENABLE_AUTO_EVOLUTION", True),
            "enable_validation_guard": _env_bool("ENABLE_VALIDATION_GUARD", True),
            "log_conflicts": _env_bool("ENABLE_CONFLICT_LOGGING", True),
        }
        self._module_diagnostics: Dict[str, Dict[str, Any]] = {}
        _apply_force_enable_all_hardening_flags(self.hardening_flags)
        self._dependency_report: Dict[str, List[str]] = {"enabled": [], "disabled": []}
        self._config_validation_notes: List[str] = []
        self.decision = DecisionEngine(self)
        self.risk = OrchestratorRiskManager(self)
        self.module_coordinator = ModuleCoordinator(self)
        self.robustness_guard = RobustnessGuard(
            min_pf=float(os.getenv("WF_MIN_OOS_PF", "1.05")),
            purge=int(os.getenv("WF_PURGE_BARS", "2")),
            min_trades=int(os.getenv("WF_MIN_TRADES", "40")),
        )
        self.robustness_guard.configure_safety(
            dsr_timeout_ms=SAFETY_DSR_TIMEOUT_MS,
            dsr_cache_s=SAFETY_DSR_CACHE_S,
            wf_learning_days=SAFETY_WF_LEARNING_DAYS,
            wf_min_trades_learning=SAFETY_WF_MIN_TRADES_LEARNING,
            max_block_ratio=SAFETY_MAX_BLOCK_RATIO,
        )
        self._last_validation_guard: Dict[str, Any] = {}
        self._validation_guard_cache: Dict[str, Dict[str, Any]] = {}
        self._validation_guard_interval_s = float(os.getenv("VALIDATION_GUARD_INTERVAL_S", str(SAFETY_DSR_CACHE_S)))
        self.regime_controller = RegimeController(
            hysteresis_ticks=int(os.getenv("REGIME_HYSTERESIS_TICKS", "3"))
        )
        self.risk_cluster_manager = RiskClusterManager(
            cluster_cap=float(os.getenv("CLUSTER_CAP_RATIO", "0.35"))
        )
        self.safety_guard = SafetyGuard(
            emergency_cycle_ms=SAFETY_EMERGENCY_CYCLE_MS,
            emergency_consecutive=SAFETY_EMERGENCY_CONSECUTIVE,
        )

        # Validator
        self.validator = ValidatorEngine()

        # Performance Ultra (Task #35 & #37)
        SystemOptimizer.optimize_for_hetzner()
        self.ofi = OrderFlowImbalance()
        SystemOptimizer.optimize_for_hetzner()

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

        # Universe manager (Lot 1) - disabled by default for safe rollout
        self.universe_manager: Optional[UniverseManager] = None
        self.pair_ranking_engine: Optional[PairRankingEngine] = None
        if ENABLE_UNIVERSE_MANAGER:
            self.universe_manager = UniverseManager(
                max_supported=UNIVERSE_MAX_SUPPORTED,
                max_eligible=UNIVERSE_MAX_ELIGIBLE,
                enable_forex=UNIVERSE_ENABLE_FOREX,
            )
            self.universe_manager.initialize()
            if ENABLE_PAIR_RANKING_ENGINE:
                self.pair_ranking_engine = PairRankingEngine(
                    universe_manager=self.universe_manager,
                    update_seconds=RANKING_UPDATE_SECONDS,
                    min_score_activate=RANKING_MIN_SCORE_ACTIVATE,
                )

        self.scalability_guard: Optional[ScalabilityGuard] = None
        self.scalability_guard_state = ScalingState.ALLOW_SCALE_UP
        self._scalability_guard_last: Dict[str, Any] = {
            "state": self.scalability_guard_state.value,
            "reasons": [],
            "signals": {},
        }
        self._global_kill_store: Optional[GlobalKillSwitchStore] = None
        if ENABLE_SCALABILITY_GUARD:
            self.scalability_guard = ScalabilityGuard(
                GuardThresholds(
                    cpu_pct_max=SCALING_GUARD_CPU_PCT_MAX,
                    memory_pct_max=SCALING_GUARD_MEMORY_PCT_MAX,
                    ws_stale_seconds_max=SCALING_GUARD_WS_STALE_SECONDS_MAX,
                    ws_lag_max=SCALING_GUARD_WS_LAG_MAX,
                    execution_failure_rate_max=SCALING_GUARD_EXEC_FAILURE_RATE_MAX,
                    reconciliation_mismatch_max=SCALING_GUARD_RECON_MISMATCH_MAX,
                )
            )
            try:
                self._global_kill_store = GlobalKillSwitchStore()
            except Exception:
                self._global_kill_store = None

        self.instance_activation_manager: Optional[InstanceActivationManager] = None
        self._activation_target_instances = self.config["max_instances"] if hasattr(self, "config") else 2000
        self._activation_last: Dict[str, Any] = {
            "action": "hold",
            "target_instances": 1,
            "target_tier": 1,
            "selected_symbols": [],
            "reason": "disabled",
        }
        if ENABLE_INSTANCE_ACTIVATION_MANAGER:
            self.instance_activation_manager = InstanceActivationManager(
                default_tier=ACTIVATION_DEFAULT_TIER,
                promote_score_min=ACTIVATION_PROMOTE_SCORE_MIN,
                demote_score_max=ACTIVATION_DEMOTE_SCORE_MAX,
                promote_health_min=ACTIVATION_PROMOTE_HEALTH_MIN,
                demote_health_max=ACTIVATION_DEMOTE_HEALTH_MAX,
                hysteresis_cycles=ACTIVATION_HYSTERESIS_CYCLES,
                cooldown_seconds=ACTIVATION_COOLDOWN_SECONDS,
            )
            self._activation_target_instances = self.instance_activation_manager.current_tier
            self._activation_last.update({
                "target_instances": self._activation_target_instances,
                "target_tier": self._activation_target_instances,
                "reason": "enabled_default",
            })

        self.portfolio_allocator: Optional[PortfolioAllocator] = None
        self._portfolio_plan: Optional[AllocationPlan] = None
        if ENABLE_PORTFOLIO_ALLOCATOR:
            self.portfolio_allocator = PortfolioAllocator(
                AllocationConstraints(
                    max_capital_per_instance_ratio=PORTFOLIO_MAX_CAPITAL_PER_INSTANCE_RATIO,
                    max_capital_per_cluster_ratio=PORTFOLIO_MAX_CAPITAL_PER_CLUSTER_RATIO,
                    reserve_cash_ratio=PORTFOLIO_RESERVE_CASH_RATIO,
                    max_total_active_risk_ratio=PORTFOLIO_MAX_TOTAL_ACTIVE_RISK_RATIO,
                    risk_per_capital_ratio=PORTFOLIO_RISK_PER_CAPITAL_RATIO,
                )
            )
        self.lifecycle_service = InstanceLifecycleService()
        self.background_tasks = BackgroundTasksService()
        self.reporting_service = ReportingService(self.daily_reporter)
        self.decision_journal_service = DecisionJournalService(
            journal=self.decision_journal,
            enabled=self._decision_journal_enabled,
        )
        self.scalability_guard_service = ScalabilityGuardService(self.scalability_guard)
        self.instance_activation_service = InstanceActivationService(self.instance_activation_manager)
        self.portfolio_allocation_service = PortfolioAllocationService(
            self.portfolio_allocator,
            self.risk_cluster_manager,
        )
        self.safety_service = SafetyService(
            safety_guard=self.safety_guard,
            robustness_guard=self.robustness_guard,
            hardening_flags=self.hardening_flags,
            reset_flag_reader=lambda: _env_bool("SAFETY_EMERGENCY_RESET", False),
        )

        # Market selector (reuse sync version)
        try:
            from .market_selector import get_market_selector
            self.market_selector = get_market_selector(self)
        except Exception:
            self.market_selector = None

        # Module manager -- conditional activation of all optional modules
        self.module_manager = ModuleManager()
        self.module_coordinator.initialize_modules()
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
            self.hardening_flags["enable_xgboost"] = (
                self.hardening_flags["enable_xgboost"]
                and self.module_manager.config.get("xgboost_predictor", False)
            )
            self.hardening_flags["enable_onchain"] = (
                self.hardening_flags["enable_onchain"]
                and self.module_manager.config.get("onchain_data", False)
            )
        self._validate_dependencies()
        logger.info("🛡️ Hardening flags: %s", self.hardening_flags)
        logger.info(
            "🤖 Autonomous mode=%s decision_policy=%s",
            self.autonomous_mode,
            self.decision_policy,
        )
        logger.info("⚙️ Runtime constraints=%s", self.runtime_constraints)
        self._validate_runtime_configuration()
        logger.info(
            "🧪 Modules activés: %s, désactivés: %s",
            len(self._dependency_report["enabled"]),
            len(self._dependency_report["disabled"]),
        )

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

    def _quick_ping(self, url: str, timeout: float = 1.5) -> bool:
        return self.module_coordinator._quick_ping(url, timeout)

    def _validate_dependencies(self) -> None:
        self._dependency_report = self.module_coordinator.validate_dependencies()

    def _record_module_event(self, module: str, status: str, error: Optional[str] = None) -> None:
        info = self._module_diagnostics.setdefault(
            module,
            {"ok": 0, "warning": 0, "error": 0, "last_status": None, "last_error": None, "last_ts": None},
        )
        if status in ("ok", "warning", "error"):
            info[status] = int(info.get(status, 0)) + 1
        info["last_status"] = status
        info["last_error"] = error
        info["last_ts"] = datetime.now(timezone.utc).isoformat()

    def _init_shadow_manager(self) -> Optional[ShadowTradingManager]:
        """Initialize or reuse shadow manager with strict paper safeguards."""
        if not self.hardening_flags.get("enable_shadow_trading", True):
            logger.info("🕶️ ShadowTradingManager désactivé par dépendances/runtime flags")
            return None
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

        initial_capital = float(os.getenv("INITIAL_CAPITAL", "1000.0"))
        default_shadow_capital = max(0.0, initial_capital * 0.20)
        shadow_capital = float(os.getenv("SHADOW_CAPITAL_POOL", str(default_shadow_capital)))
        shadow_capital = max(0.0, min(shadow_capital, default_shadow_capital))
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

        max_instances_cap = self.config["max_instances"]
        if self.instance_activation_manager is not None:
            max_instances_cap = max(1, int(self._activation_target_instances))
        if len(self._instances) >= max_instances_cap:
            logger.warning(f"⚠️ Limite instances: {max_instances_cap}")
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

            # P1: Order Flow Imbalance (OFI) subscription
            if self.ofi:
                book_client = getattr(self, "_ws", None) or getattr(self, "ws_client", None)
                subscribe_book = getattr(book_client, "subscribe_book", None)
                if subscribe_book:
                    await subscribe_book(config.symbol, self.ofi.on_book_update)
                else:
                    logger.debug("OFI book subscription skipped: websocket client has no book channel")
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
        if self.scalability_guard is not None and self.scalability_guard_state != ScalingState.ALLOW_SCALE_UP:
            logger.info("⏳ Spin-off bloqué par ScalabilityGuard: %s", self.scalability_guard_state.value)
            self._journal_rejected_opportunity(
                reason=REJECTION_REASON_SCALABILITY_GUARD_BLOCK,
                source="check_spin_off",
                symbol=str(parent.config.symbol),
                context={
                    "parent_instance_id": parent.id,
                    "guard_state": self.scalability_guard_state.value,
                },
            )
            return None

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
        """Get unallocated cash from the live/paper balance source."""
        snapshot = await self.get_capital_snapshot()
        return float(snapshot.get("available_cash", 0.0))

    async def get_capital_snapshot(self) -> Dict[str, Any]:
        """Return the backend source of truth for dashboard capital values."""
        allocated_capital = sum(
            float(inst.get_current_capital()) for inst in self._instances.values()
        )
        total_profit = sum(
            float(getattr(inst, "get_profit", lambda: 0.0)()) for inst in self._instances.values()
        )
        open_position_notional = 0.0
        for inst in self._instances.values():
            try:
                for pos in inst.get_positions_snapshot():
                    if pos.get("status") == "open":
                        open_position_notional += float(pos.get("buy_price", 0.0)) * float(pos.get("volume", 0.0))
            except Exception:
                continue

        source = "paper" if self.paper_mode else "kraken"
        try:
            balances = await self.order_executor.get_balance()
            cash_balance = float(balances.get("ZEUR", balances.get("EUR", 0.0)))
            total_balance = cash_balance
            if self.paper_mode and hasattr(self.order_executor, "get_trade_balance"):
                trade_balance = await self.order_executor.get_trade_balance("EUR")
                total_balance = float(trade_balance.get("equivalent_balance", cash_balance))
            reserve_cash = max(0.0, total_balance - allocated_capital)
            snapshot = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "paper_mode": self.paper_mode,
                "source": source,
                "source_status": "ok",
                "currency": "EUR",
                "total_balance": total_balance,
                "total_capital": total_balance,
                "allocated_capital": allocated_capital,
                "reserve_cash": reserve_cash,
                "available_cash": reserve_cash,
                "cash_balance": cash_balance,
                "open_position_notional": open_position_notional,
                "total_profit": total_profit,
                "total_invested": allocated_capital,
                "balances": balances,
            }
        except Exception as exc:
            logger.error(f"❌ Erreur récupération balance: {exc}")
            snapshot = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "paper_mode": self.paper_mode,
                "source": source,
                "source_status": "unavailable",
                "currency": "EUR",
                "total_balance": 0.0,
                "total_capital": 0.0,
                "allocated_capital": allocated_capital,
                "reserve_cash": 0.0,
                "available_cash": 0.0,
                "cash_balance": 0.0,
                "open_position_notional": open_position_notional,
                "total_profit": total_profit,
                "total_invested": allocated_capital,
                "error": str(exc),
            }
        self._last_capital_snapshot = snapshot
        return snapshot

    async def _evaluate_scalability_guard(self) -> None:
        if self.scalability_guard is None:
            return

        cpu_pct = 0.0
        memory_pct = 0.0
        try:
            import psutil

            cpu_pct = float(psutil.cpu_percent(interval=0.0))
            memory_pct = float(psutil.virtual_memory().percent)
        except Exception:
            pass

        ws_connected = bool(self.ws_client.is_connected())
        ws_stale_seconds = 0.0
        ws_lag = 0
        try:
            fresh = bool(self.ring_dispatcher.is_data_fresh(SCALING_GUARD_WS_STALE_SECONDS_MAX))
            ws_stale_seconds = 0.0 if fresh else float(SCALING_GUARD_WS_STALE_SECONDS_MAX + 1.0)
            ws_lag = int(getattr(self.ring_dispatcher, "stats", {}).get("total_lag", 0))
        except Exception:
            pass

        failures = sum(float(v.get("failures", 0.0)) for v in self._module_backoff.values())
        total_actions = max(
            1.0,
            float(self._decision_stats.get("entry_actions", 0)
            + self._decision_stats.get("add_actions", 0)
            + self._decision_stats.get("exit_actions", 0)),
        )
        execution_failure_rate = min(1.0, failures / total_actions)

        reconciliation_mismatch_ratio = 0.0
        try:
            rec_stats = self.reconciliation_manager.get_stats() if self.reconciliation_manager else {}
            if rec_stats and not rec_stats.get("is_running", True):
                reconciliation_mismatch_ratio = 1.0
        except Exception:
            pass

        kill_switch_tripped = bool(self.safety_guard.emergency_mode)
        if not kill_switch_tripped and self._global_kill_store is not None:
            try:
                kill_switch_tripped = bool(self._global_kill_store.get().tripped)
            except Exception:
                kill_switch_tripped = False

        running_instances = [inst for inst in self._instances.values() if inst.is_running()]
        pf_degraded = False
        if running_instances:
            avg_pf = sum(float(inst.get_profit_factor_days(30)) for inst in running_instances) / len(running_instances)
            pf_degraded = avg_pf < SCALING_GUARD_PF_MIN

        validation_degraded = False
        if self._last_validation_guard:
            fails = sum(1 for v in self._last_validation_guard.values() if not bool(v.get("passed", True)))
            validation_degraded = (fails / max(1, len(self._last_validation_guard))) > SCALING_GUARD_VALIDATION_FAIL_MAX

        decision = self.scalability_guard_service.evaluate(
            ScalabilityMetrics(
                cpu_pct=cpu_pct,
                memory_pct=memory_pct,
                ws_connected=ws_connected,
                ws_stale_seconds=ws_stale_seconds,
                ws_total_lag=ws_lag,
                execution_failure_rate=execution_failure_rate,
                reconciliation_mismatch_ratio=reconciliation_mismatch_ratio,
                kill_switch_tripped=kill_switch_tripped,
                pf_degraded=pf_degraded,
                validation_degraded=validation_degraded,
            )
        )
        if decision is None:
            return
        self.scalability_guard_state = decision.state
        self._scalability_guard_last = {
            "state": decision.state.value,
            "reasons": list(decision.reasons),
            "signals": dict(decision.signals),
        }
        guard_fp = self._fingerprint(
            {
                "state": decision.state.value,
                "reasons": list(decision.reasons),
            }
        )
        if (
            decision.state.value != self._journal_last_guard_state
            or guard_fp != self._journal_last_guard_fp
        ):
            self._journal_last_guard_state = decision.state.value
            self._journal_last_guard_fp = guard_fp
            self._journal_major_decision(
                decision_type="guard_decision",
                source="scalability_guard",
                reasons=list(decision.reasons),
                context={
                    "state": decision.state.value,
                    "signals": dict(decision.signals),
                },
            )

    async def _apply_instance_activation_policy(self) -> None:
        if self.instance_activation_manager is None:
            return

        ranked_symbols: List[str] = []
        scored_map: Dict[str, Dict[str, Any]] = {}
        if self.pair_ranking_engine is not None:
            ranked_symbols = list(self.pair_ranking_engine.get_active_symbols())
            scored_map = self.universe_manager.get_scored_universe() if self.universe_manager else {}
        elif self.universe_manager is not None:
            ranked_symbols = list(self.universe_manager.get_ranked_universe())
            scored_map = self.universe_manager.get_scored_universe()

        if not ranked_symbols:
            ranked_symbols = sorted({inst.config.symbol for inst in self._instances.values()})

        score_values = [
            float(scored_map.get(sym, {}).get("score", 0.0))
            for sym in ranked_symbols
            if sym in scored_map
        ]
        avg_rank_score = (sum(score_values) / len(score_values)) if score_values else 0.0
        below_threshold_symbols = self.instance_activation_service.below_threshold_symbols(
            ranked_symbols,
            scored_map,
        )
        if below_threshold_symbols:
            low_fp = self._fingerprint(
                {
                    "symbols": below_threshold_symbols[: journal_symbol_cap()],
                    "threshold": float(RANKING_MIN_SCORE_ACTIVATE),
                }
            )
            if low_fp != self._journal_last_rejected_ranking_fp:
                self._journal_last_rejected_ranking_fp = low_fp
                for sym in below_threshold_symbols[: journal_symbol_cap()]:
                    self._journal_rejected_opportunity(
                        reason=REJECTION_REASON_RANKING_BELOW_THRESHOLD,
                        source="instance_activation_policy",
                        symbol=sym,
                        context={
                            "score": float(scored_map.get(sym, {}).get("score", 0.0)),
                            "min_score_activate": float(RANKING_MIN_SCORE_ACTIVATE),
                        },
                    )

        activation_result = self.instance_activation_service.apply(
            ActivationContext(
                ranked_symbols=ranked_symbols,
                scored_map=scored_map,
                guard_state=self.scalability_guard_state,
                health_score=self._compute_health_score(),
                running_instances=len([i for i in self._instances.values() if i.is_running()]),
                now_ts=perf_counter(),
            )
        )
        if activation_result is None:
            return
        decision = activation_result.payload
        self._activation_target_instances = int(activation_result.target_instances)
        self._activation_last = {
            "action": decision["action"],
            "target_instances": self._activation_target_instances,
            "target_tier": int(decision["target_tier"]),
            "selected_symbols": list(decision["selected_symbols"]),
            "reason": decision["reason"],
        }
        if decision["action"] in {"promote", "demote", "freeze"}:
            self._journal_major_decision(
                decision_type="activation_decision",
                source="instance_activation_manager",
                symbols=list(decision["selected_symbols"][: journal_symbol_cap()]),
                reasons=[decision["reason"]],
                context={
                    "action": decision["action"],
                    "target_instances": int(self._activation_target_instances),
                    "target_tier": int(decision["target_tier"]),
                    "avg_rank_score": float(avg_rank_score),
                    "guard_state": self.scalability_guard_state.value,
                    "running_instances": len([i for i in self._instances.values() if i.is_running()]),
                },
            )
        if decision["action"] in {"promote", "demote", "freeze"}:
            for sym in activation_result.rejected_symbols[: max(0, journal_symbol_cap() - len(decision["selected_symbols"]))]:
                self._journal_rejected_opportunity(
                    reason=REJECTION_REASON_SYMBOL_NOT_SELECTED,
                    source="instance_activation_policy",
                    symbol=str(sym),
                    context={
                        "action": decision["action"],
                        "target_tier": int(decision["target_tier"]),
                    },
                )

        # Demote path: reduce non-parent instances to target cap (conservative).
        running = [
            inst for inst in self.lifecycle_service.running_instances(self._instances.values())
            if inst.id != self.parent_instance_id
        ]
        excess = max(0, len(self._instances) - self._activation_target_instances)
        if excess > 0:
            victims = self.lifecycle_service.select_worst_by_pf(running, excess)
            for victim in victims:
                await self.remove_instance(victim.id)

    def _refresh_portfolio_allocation_plan(self) -> None:
        if self.portfolio_allocation_service.allocator is None:
            self._portfolio_plan = None
            return

        active_instances = [inst for inst in self._instances.values() if inst.is_running()]
        ranked_symbols: List[str] = []
        if isinstance(self._activation_last.get("selected_symbols"), list):
            ranked_symbols = [str(s) for s in self._activation_last.get("selected_symbols", [])]
        if not ranked_symbols and self.pair_ranking_engine is not None:
            ranked_symbols = list(self.pair_ranking_engine.get_active_symbols())
        if not ranked_symbols:
            ranked_symbols = sorted({inst.config.symbol for inst in active_instances})

        self._portfolio_plan = self.portfolio_allocation_service.refresh_plan(
            instances=active_instances,
            fallback_instances=self._instances.values(),
            ranked_symbols=ranked_symbols,
        )
        if self._portfolio_plan is not None:
            top_symbols = list(self._portfolio_plan.symbol_caps.keys())[: journal_symbol_cap()]
            fp = self._fingerprint(
                {
                    "symbol_caps": {k: round(float(v), 2) for k, v in self._portfolio_plan.symbol_caps.items()},
                    "reasons": dict(self._portfolio_plan.reasons),
                    "risk_budget_remaining": round(float(self._portfolio_plan.risk_budget_remaining), 6),
                }
            )
            if fp != self._journal_last_allocation_fp:
                self._journal_last_allocation_fp = fp
                self._journal_major_decision(
                    decision_type="allocation_decision",
                    source="portfolio_allocator",
                    symbols=top_symbols,
                    reasons=list(self._portfolio_plan.reasons.values()),
                    context={
                        "total_allocated": float(self._portfolio_plan.total_allocated),
                        "reserve_cash": float(self._portfolio_plan.reserve_cash),
                        "risk_budget_remaining": float(self._portfolio_plan.risk_budget_remaining),
                        "symbol_caps": {
                            k: float(v)
                            for k, v in list(self._portfolio_plan.symbol_caps.items())[: journal_symbol_cap()]
                        },
                    },
                )

    async def _apply_force_reduce_once(self) -> None:
        """Conservative scale-down when guard is in FORCE_REDUCE state."""
        removable = [
            inst for iid, inst in self._instances.items()
            if iid != self.parent_instance_id and inst.is_running()
        ]
        if not removable:
            return
        worst_candidates = self.lifecycle_service.select_worst_by_pf(removable, 1)
        if not worst_candidates:
            return
        worst = worst_candidates[0]
        self._journal_major_decision(
            decision_type="guard_force_reduce",
            source="scalability_guard",
            symbols=[str(worst.config.symbol)],
            reasons=["force_reduce_remove_worst_pf"],
            context={
                "instance_id": worst.id,
                "pf30": float(getattr(worst, "get_profit_factor_days", lambda _d: 1.0)(30)),
            },
        )
        await self.remove_instance(worst.id)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _main_loop(self) -> None:
        logger.info("🚀 OrchestratorAsync main loop démarré")
        while self.running:
            try:
                if self.pair_ranking_engine is not None:
                    self.pair_ranking_engine.refresh_if_due()
                    ranked_symbols = list(self.pair_ranking_engine.get_active_symbols())
                    scored_map = self.universe_manager.get_scored_universe() if self.universe_manager else {}
                    top_symbols = ranked_symbols[: max(1, int(DECISION_JOURNAL_MAX_SYMBOLS))]
                    score_snapshot = {
                        sym: float(scored_map.get(sym, {}).get("score", 0.0))
                        for sym in top_symbols
                    }
                    fp = self._fingerprint({"top_symbols": top_symbols, "scores": score_snapshot})
                    if fp != self._journal_last_ranking_fp:
                        self._journal_last_ranking_fp = fp
                        self._journal_major_decision(
                            decision_type="ranking_decision",
                            source="pair_ranking_engine",
                            symbols=top_symbols,
                            reasons=["ranking_refresh"],
                            context={
                                "top_symbols_count": len(top_symbols),
                                "min_score_activate": float(RANKING_MIN_SCORE_ACTIVATE),
                                "scores": score_snapshot,
                            },
                        )
                await self._evaluate_scalability_guard()
                await self._apply_instance_activation_policy()
                self._refresh_portfolio_allocation_plan()
                if self.scalability_guard_state == ScalingState.FORCE_REDUCE:
                    await self._apply_force_reduce_once()
                instances = self.decision.select_instances_for_cycle()
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

        exits_count = await self.risk.check_exit_conditions(inst)
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
        opened = await self.decision.evaluate_signal(inst)
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
        add_count = await self.risk.evaluate_add_position(inst)
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
        if not self.safety_guard.check_performance_budget(self._loop_metrics["process_cycle_ms"]):
            self._activate_emergency_mode("cycle budget exceeded")

    def _journal_major_decision(
        self,
        *,
        decision_type: str,
        source: str,
        symbols: Optional[List[str]] = None,
        reasons: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.decision_journal_service.major_decision(
            decision_type=decision_type,
            source=source,
            symbols=symbols or [],
            reasons=reasons or [],
            context=context or {},
        )

    def _journal_rejected_opportunity(
        self,
        *,
        reason: str,
        source: str,
        symbol: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        symbols = [str(symbol)] if symbol else []
        self._journal_major_decision(
            decision_type="rejected_opportunity",
            source=source,
            symbols=symbols,
            reasons=[reason],
            context=context or {},
        )

    def _fingerprint(self, payload: Any) -> str:
        return self.decision_journal_service.fingerprint(payload)

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
        return self.module_coordinator.module_can_run(name)

    def _module_record_success(self, name: str) -> None:
        self.module_coordinator.module_record_success(name)

    def _module_record_failure(self, name: str) -> None:
        self.module_coordinator.module_record_failure(name)

    def _update_pair_risk_state(self, instance: TradingInstanceAsync) -> None:
        """
        Maintain lightweight EMA state per symbol to calibrate risk by pair.
        """
        symbol = str(getattr(instance.config, "symbol", "UNKNOWN"))
        pf = float(instance.get_profit_factor_days(30))
        dd = float(instance.get_drawdown())
        state = self._pair_risk_state.setdefault(
            symbol,
            {"pf_ema": pf, "dd_ema": dd, "last_price": None},
        )
        alpha = 0.2
        state["pf_ema"] = (alpha * pf) + ((1 - alpha) * float(state["pf_ema"]))
        state["dd_ema"] = (alpha * dd) + ((1 - alpha) * float(state["dd_ema"]))
        price = float(instance.get_status().get("last_price") or 0.0)
        last_price = float(state.get("last_price") or 0.0)
        if price > 0 and last_price > 0:
            ret = (price - last_price) / last_price
            if abs(ret) >= 5.0:
                logger.debug("return outlier skipped for %s", symbol)
        state["last_price"] = price if price > 0 else last_price

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

    def _activate_emergency_mode(self, reason: str) -> None:
        self.safety_service.activate_emergency_mode(reason, logger)

    def _reset_emergency_mode(self) -> None:
        self.safety_service.reset_emergency_mode()

    async def _check_cycle_health(self) -> None:
        await self.safety_service.monitor_cycle_health(
            running=lambda: self.running,
            loop_metrics=self._loop_metrics,
            on_activate=self._activate_emergency_mode,
            logger=logger,
        )

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
                self._journal_major_decision(
                    decision_type="entry_block_decision",
                    source="black_swan_guard",
                    symbols=[str(instance.config.symbol)],
                    reasons=[str(event.get("type", "unknown"))],
                    context={"instance_id": instance.id, "event": dict(event)},
                )
                self._journal_rejected_opportunity(
                    reason=REJECTION_REASON_BLACK_SWAN_EMERGENCY_BLOCK,
                    source="black_swan_guard",
                    symbol=str(instance.config.symbol),
                    context={"instance_id": instance.id, "event": dict(event)},
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

    def _passes_validation_guard(self, instance: TradingInstanceAsync) -> bool:
        if self.safety_guard.emergency_mode:
            return True
        if not self.hardening_flags.get("enable_validation_guard", True):
            return True
        now = perf_counter()
        cached = self._validation_guard_cache.get(instance.id)
        if cached and (now - float(cached.get("ts", 0.0))) < self._validation_guard_interval_s:
            cached_result = dict(cached.get("result", {}))
            self._last_validation_guard[instance.id] = cached_result
            return cached_result.get("pass", 0.0) >= 0.5
        trades = list(getattr(instance, "_trades", []))
        pnls = [float(getattr(t, "profit", 0.0) or 0.0) for t in trades]
        first_seen = self._instance_first_seen_ts.setdefault(instance.id, now)
        age_days = int(max(0.0, (now - first_seen) / 86400.0))
        result = self.robustness_guard.evaluate(
            pnls,
            instance_age_days=age_days,
            emergency_mode=self.safety_guard.emergency_mode,
        )
        self._validation_guard_cache[instance.id] = {"ts": now, "result": result}
        self._last_validation_guard[instance.id] = result
        if result.get("pass", 0.0) < 0.5:
            now_utc = datetime.now(timezone.utc)
            if (now_utc - self._wf_window_start).total_seconds() >= 86400:
                self._wf_window_start = now_utc
                self._wf_blocked_24h = 0
            self._wf_blocked_24h += 1
            self._record_module_event(
                "validation_guard",
                "warning",
                f"blocked wf_pf={result.get('wf_oos_pf', 0.0):.3f} dsr={result.get('dsr', 0.0):.3f}",
            )
            self._journal_major_decision(
                decision_type="entry_block_decision",
                source="validation_guard",
                symbols=[str(instance.config.symbol)],
                reasons=["validation_guard_blocked"],
                context={
                    "instance_id": instance.id,
                    "wf_oos_pf": float(result.get("wf_oos_pf", 0.0)),
                    "dsr": float(result.get("dsr", 0.0)),
                    "pass_score": float(result.get("pass", 0.0)),
                    "blocked_24h": int(self._wf_blocked_24h),
                },
            )
            self._journal_rejected_opportunity(
                reason=REJECTION_REASON_VALIDATION_GUARD_BLOCK,
                source="validation_guard",
                symbol=str(instance.config.symbol),
                context={
                    "instance_id": instance.id,
                    "wf_oos_pf": float(result.get("wf_oos_pf", 0.0)),
                    "dsr": float(result.get("dsr", 0.0)),
                },
            )
            return False
        self._record_module_event("validation_guard", "ok")
        return True

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
            regime_state = self.regime_controller.update(
                symbol=str(instance.config.symbol),
                trend=trend,
                volatility=float(instance.get_volatility()),
                drawdown=float(instance.get_drawdown()),
            )
            module_policy = self.regime_controller.module_policy(regime_state.regime)
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
            if (
                self.hardening_flags["enable_mean_reversion"]
                and not self.safety_guard.emergency_mode
                and module_policy.get("enable_mean_reversion", True)
                and mr and trend == "range"
            ):
                mr.update(price)
                mr_signal = "BUY" if mr.should_enter() else "HOLD"
            logger.info("MeanReversion signal: %s", mr_signal)

            # Sentiment update/read (timeout strict 5s)
            sentiment_score = 0.0
            if (
                self.hardening_flags["enable_sentiment"]
                and not self.safety_guard.emergency_mode
                and self._module_can_run("sentiment")
            ):
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
                    self.voter.submit_vote("sentiment", "BUY" if sentiment_score > 0 else "SELL", confidence=abs(sentiment_score))
                    logger.info("Sentiment: %.3f", sentiment_score)
                    self._module_record_success("sentiment")
                except Exception as exc:
                    logger.warning("Sentiment unavailable (isolé): %s", exc)
                    self._module_record_failure("sentiment")

            # On-chain feature (best effort)
            if (
                self.hardening_flags.get("enable_onchain", False)
                and not self.safety_guard.emergency_mode
                and module_policy.get("enable_onchain", True)
                and self._module_can_run("onchain")
            ):
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
            if (
                self.hardening_flags["enable_ml"]
                and not self.safety_guard.emergency_mode
                and module_policy.get("enable_ml", True)
                and self._module_can_run("xgboost")
            ):
                try:
                    features = self.xgboost.extract_features(price=price, volume=volume)
                    if features is not None:
                        features_ext = list(features) + [onchain_score]
                        prediction = self.xgboost.predict(features_ext)
                        if prediction is not None:
                            ml_confidence = float(prediction.get("probability", 0.0))
                            ml_direction = "BUY" if prediction.get("direction") == "UP" else "SELL"
                            self.voter.submit_vote("xgboost", ml_direction, confidence=ml_confidence)
                        else:
                            self.heuristic_predictor.update(price=price, volume=volume)
                            hp = self.heuristic_predictor.predict()
                            if hp is not None:
                                ml_confidence = float(hp.confidence)
                                ml_direction = "BUY" if hp.probability_up >= 0.5 else "SELL"
                                self.voter.submit_vote("heuristic", ml_direction, confidence=ml_confidence)

                        # enrichit dataset XGBoost (label naïf basée sur tendance)
                        label = 1 if trend == "up" else 0
                        self.xgboost.add_sample(features_ext, label)
                    self._module_record_success("xgboost")
                    self.voter.tick()
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
                self._journal_major_decision(
                    decision_type="entry_block_decision",
                    source="entry_rate_guard",
                    symbols=[str(instance.config.symbol)],
                    reasons=["repeated_auto_action_limit"],
                    context={
                        "instance_id": instance.id,
                        "repeated_actions": int(repeated_actions),
                        "max_repeated_auto_actions": int(self.max_repeated_auto_actions),
                    },
                )
                self._journal_rejected_opportunity(
                    reason=REJECTION_REASON_REPEATED_AUTO_ACTION_BLOCK,
                    source="entry_rate_guard",
                    symbol=str(instance.config.symbol),
                    context={
                        "instance_id": instance.id,
                        "repeated_actions": int(repeated_actions),
                        "max_repeated_auto_actions": int(self.max_repeated_auto_actions),
                    },
                )
                return False
            if not self._can_emit_trade_action(instance.id):
                logger.info(
                    "⏱️ Trade action throttled for %s (min interval %.2fs)",
                    instance.id,
                    self.trade_action_min_interval_s,
                )
                return False
            if not self._passes_validation_guard(instance):
                logger.warning("🧪 Validation guard blocked entry for %s", instance.id)
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
                self.voter.tick()
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
            active_instances = [inst for inst in self._instances.values() if inst.is_running()]
            exposures = self.risk_cluster_manager.exposure_by_cluster(active_instances)
            total_capital = sum(max(0.0, float(inst.get_current_capital())) for inst in active_instances) or capital
            cluster_mult = self.risk_cluster_manager.allowed_multiplier(
                symbol=str(instance.config.symbol),
                add_size=float(final_size),
                total_capital=float(total_capital),
                exposures=exposures,
            )
            final_size *= cluster_mult
            if cluster_mult < 1.0:
                self._record_module_event(
                    "cluster_risk_cap",
                    "warning",
                    f"symbol={instance.config.symbol} cluster_mult={cluster_mult:.3f}",
                )
            if self._portfolio_plan is not None:
                symbol = str(instance.config.symbol)
                envelope = float(self._portfolio_plan.symbol_caps.get(symbol, 0.0))
                if envelope > 0.0:
                    final_size = min(final_size, envelope)
                else:
                    final_size = 0.0
                    self._journal_rejected_opportunity(
                        reason=REJECTION_REASON_ALLOCATION_ENVELOPE_BLOCKED,
                        source="position_sizing",
                        symbol=symbol,
                        context={
                            "instance_id": instance.id,
                            "envelope": float(envelope),
                            "reason": str(self._portfolio_plan.reasons.get(symbol, "no_symbol_cap")),
                        },
                    )
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
                return 0
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
        await self.reporting_service.run_daily_report_loop(
            running=lambda: self.running,
            logger=logger,
        )

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
            await persistence.initialize()
            deleted = await persistence.cleanup_orphaned_instances(list(self._instances.keys()))
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

        # Connect WS via ring dispatcher (P2). Kraken can occasionally return
        # transient 5xx responses during the opening handshake; retry startup
        # before declaring the bot unavailable.
        await self._connect_ring_dispatcher_with_retry()

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
        self.background_tasks.start(
            {
                "daily_report": self._daily_report_loop,
                "xgboost_train": self._train_xgboost_loop,
                "sentiment_update": self._sentiment_update_loop,
                "cycle_health": self._check_cycle_health,
            }
        )
        self._daily_report_task = self.background_tasks.tasks.get("daily_report")
        self._xgboost_train_task = self.background_tasks.tasks.get("xgboost_train")
        self._sentiment_task = self.background_tasks.tasks.get("sentiment_update")
        self._cycle_health_task = self.background_tasks.tasks.get("cycle_health")

        if self.paper_mode:
            total_capital = sum(
                float(inst.get_current_capital()) for inst in self._instances.values()
            ) + float(getattr(self.shadow_manager, "_shadow_capital_pool", 0.0) if self.shadow_manager else 0.0)
            initial_capital = float(os.getenv("INITIAL_CAPITAL", "1000.0"))
            if total_capital > initial_capital:
                logger.warning(
                    "🕶️ Capital total paper+shadow %.2f€ > %.2f€ (limite paper)",
                    total_capital,
                    initial_capital,
                )
            self.background_tasks.start(
                {
                    "shadow_promotion": self._check_shadow_promotions,
                    "rebalance": self._rebalance_loop,
                    "auto_evolution": self._auto_evolution_loop,
                }
            )
            self._shadow_promotion_task = self.background_tasks.tasks.get("shadow_promotion")
            self._rebalance_task = self.background_tasks.tasks.get("rebalance")
            self._auto_evolution_task = self.background_tasks.tasks.get("auto_evolution")
            logger.info("🧪 Advanced modules activés en PAPER_TRADING=true")
        else:
            logger.warning("🧪 Advanced modules désactivés (PAPER_TRADING=false)")

        # Start instances
        for inst in list(self._instances.values()):
            await inst.start()

        # Main loop
        self._main_task = asyncio.create_task(self._main_loop())
        logger.info("✅ OrchestratorAsync démarré (P4: hot/cold path actif)")

    async def _connect_ring_dispatcher_with_retry(self) -> None:
        max_attempts = max(1, int(os.getenv("WS_CONNECT_RETRIES", "6")))
        delay_s = max(0.5, float(os.getenv("WS_CONNECT_RETRY_DELAY_S", "5.0")))
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                await self.ring_dispatcher.connect()
                if attempt > 1:
                    logger.info("✅ WebSocket connecté après %d tentative(s)", attempt)
                return
            except Exception as exc:
                last_error = exc
                self._module_diagnostics["websocket_startup"] = {
                    "status": "retrying" if attempt < max_attempts else "error",
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error": str(exc)[:240],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                if attempt >= max_attempts:
                    break
                logger.warning(
                    "⚠️ Connexion WebSocket échouée au démarrage (%d/%d): %s. Nouvelle tentative dans %.1fs",
                    attempt,
                    max_attempts,
                    exc,
                    delay_s,
                )
                await asyncio.sleep(delay_s)
                delay_s = min(delay_s * 1.7, 45.0)

        raise last_error if last_error else RuntimeError("Connexion WebSocket impossible")

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
        await self.background_tasks.stop()
        self._daily_report_task = None
        self._xgboost_train_task = None
        self._sentiment_task = None
        self._cycle_health_task = None
        self._shadow_promotion_task = None
        self._rebalance_task = None
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
        self.decision_journal.close()

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
        status = {
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
            "decision_journal": {
                "enabled": bool(self._decision_journal_enabled),
                "path": str(getattr(self.decision_journal, "path", "")),
            },
            "decision_policy": dict(self.decision_policy),
            "loop_metrics_ms": dict(self._loop_metrics),
            "decision_stats": dict(self._decision_stats),
            "last_decision": dict(self._last_decision),
            "module_diagnostics": dict(self._module_diagnostics),
            "validation_guard": dict(self._last_validation_guard),
            "regime_state": self.regime_controller.snapshot(),
            "cluster_exposure": self.risk_cluster_manager.exposure_by_cluster(
                [inst for inst in self._instances.values() if inst.is_running()]
            ),
            "scalability_guard": dict(self._scalability_guard_last),
            "activation": dict(self._activation_last),
            "portfolio_allocator": {
                "enabled": self.portfolio_allocator is not None,
                "plan": {
                    "symbol_caps": dict(self._portfolio_plan.symbol_caps),
                    "total_allocated": float(self._portfolio_plan.total_allocated),
                    "reserve_cash": float(self._portfolio_plan.reserve_cash),
                    "risk_budget_remaining": float(self._portfolio_plan.risk_budget_remaining),
                    "reasons": dict(self._portfolio_plan.reasons),
                    "explain": dict(self._portfolio_plan.explain),
                } if self._portfolio_plan else None,
            },
            "capital": dict(self._last_capital_snapshot),
            "safety": {
                "emergency_mode": self.safety_guard.emergency_mode,
                "dsr_last_ms": float(self.robustness_guard._last_dsr_exec_ms),
                "dsr_cached": (perf_counter() - float(self.robustness_guard._dsr_cache.get("ts", 0.0))) <= self.robustness_guard.safety_dsr_cache_s,
                "walk_forward_blocked_24h": int(self._wf_blocked_24h),
                "cycle_time_ms": float(self._loop_metrics.get("process_cycle_ms", 0.0)),
                "features_active": [
                    name for name, enabled in {
                        "regime": True,
                        "cluster": True,
                        "walk_forward": self.hardening_flags.get("enable_validation_guard", False),
                        "dsr": self.hardening_flags.get("enable_validation_guard", False),
                    }.items() if enabled
                ],
                "features_disabled_by_safety": sorted(set(self.safety_guard.blocked_features) | {
                    name for name in ("enable_sentiment", "enable_ml", "enable_xgboost", "enable_onchain", "enable_validation_guard")
                    if self.safety_guard.emergency_mode and not self.hardening_flags.get(name, True)
                }),
                "emergency_reset": True,
            },
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
                    "symbol": s.get("symbol", getattr(inst.config, "symbol", None)),
                    "capital": s["current_capital"],
                    "profit": s["total_profit"],
                    "profit_pct": s.get("profit_pct", 0.0),
                    "drawdown": s.get("drawdown", 0.0),
                    "max_drawdown": s.get("max_drawdown", 0.0),
                    "status": s["status"],
                    "strategy": s["strategy"],
                    "open_positions": s["open_positions_count"],
                    "initial_capital": s.get("initial_capital"),
                    "warmup": s.get("warmup", {}),
                    "blocked_reasons": s.get("blocked_reasons", []),
                    "strategy_status": s.get("strategy_status", {}),
                    "last_price": s.get("last_price"),
                    "last_market_tick": s.get("last_market_tick"),
                    "last_signal": s.get("last_signal"),
                    "last_decision": s.get("last_decision"),
                    "last_order": s.get("last_order"),
                    "last_error": s.get("last_error"),
                    "runtime_events": s.get("runtime_events", []),
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
