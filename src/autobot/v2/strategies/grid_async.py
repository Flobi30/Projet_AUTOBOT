"""
Grid Strategy — Async version (V3: Adaptive Grid)
MIGRATION P0: Replaces grid.py (threading.RLock -> no lock in async)

V3 additions:
- AdaptiveRangeCalculator integration (replaces fixed range_percent)
- PairProfileRegistry support (per-pair config)
- SmartRecentering (progressive, replaces brutal DGT)
- DynamicGridAllocator (adaptive levels + capital)
- Backward compatible: falls back to legacy behaviour without config
"""

from __future__ import annotations

import logging
import math
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from . import TradingSignal, SignalType, calculate_grid_levels, PositionSizing
from ..modules.trailing_stop_atr import TrailingStopATR
from ..modules.atr_filter import ATRFilter
from .strategy_async import StrategyAsync
from ..speculative_order_cache import SpeculativeOrderCache

# V3 imports — lazy loaded to avoid circular imports at module level
_SmartRecentering = None
_AdaptiveRangeCalculator = None
_PairProfileRegistry = None
_DynamicGridAllocator = None
_GridRecenteringManager = None

logger = logging.getLogger(__name__)

# Lazy imports for modules (avoid import errors if not installed)
_RegimeDetector = None
_FundingRatesMonitor = None
_OpenInterestMonitor = None
_KellyCriterion = None


def _load_v3_modules():
    global _SmartRecentering, _AdaptiveRangeCalculator, _PairProfileRegistry
    global _DynamicGridAllocator, _GridRecenteringManager
    if _SmartRecentering is None:
        try:
            from .smart_recentering import SmartRecentering
            from .range_calculator import AdaptiveRangeCalculator
            from .adaptive_grid_config import PairProfileRegistry, DynamicGridAllocator
            _SmartRecentering = SmartRecentering
            _AdaptiveRangeCalculator = AdaptiveRangeCalculator
            _PairProfileRegistry = PairProfileRegistry
            _DynamicGridAllocator = DynamicGridAllocator
        except ImportError as e:
            logger.warning("V3 adaptive grid modules not available: %s", e)
    if _GridRecenteringManager is None:
        try:
            from ..grid_recentering import GridRecenteringManager
            _GridRecenteringManager = GridRecenteringManager
        except ImportError:
            pass


def _load_modules():
    global _RegimeDetector, _FundingRatesMonitor, _OpenInterestMonitor, _KellyCriterion
    if _RegimeDetector is None:
        try:
            from autobot.v2.modules.regime_detector import RegimeDetector
            from autobot.v2.modules.funding_rates import FundingRatesMonitor
            from autobot.v2.modules.open_interest import OpenInterestMonitor
            from autobot.v2.modules.kelly_criterion import KellyCriterion
            _RegimeDetector = RegimeDetector
            _FundingRatesMonitor = FundingRatesMonitor
            _OpenInterestMonitor = OpenInterestMonitor
            _KellyCriterion = KellyCriterion
        except ImportError as e:
            logger.warning(f"Modules grid non disponibles: {e}")


class GridStrategyAsync(StrategyAsync):
    """
    Async Grid Trading Strategy — V3 Adaptive.

    When a PairProfile is found (via config or PairProfileRegistry), the grid
    uses adaptive range, dynamic levels, and smart recentering.

    Without a profile, behaviour is 100% identical to V2 (fixed 7% range,
    15 levels, brutal DGT recentering).
    """

    def __init__(self, instance: Any, config: Optional[Dict] = None) -> None:
        super().__init__(instance, config)

        _load_v3_modules()
        _load_modules()

        self.center_price = self.config.get("center_price", None)
        self.range_percent = self.config.get("range_percent", 2.0)
        self.num_levels = self.config.get("num_levels", 15)
        self.max_capital_per_level = self.config.get("max_capital_per_level", 50.0)
        self.max_positions = self.config.get("max_positions", 10)
        self.voter_filter_active = self.config.get("voter_filter_active", True)
        self.kelly_active = self.config.get("kelly_active", True)
        self.trailing_tp_active = self.config.get("trailing_tp_active", True)
        self._block_underperforming_health = self._read_bool_config(
            "block_underperforming_health",
            "GRID_BLOCK_UNDERPERFORMING_HEALTH",
            True,
        )
        self._setup_optimizer_execution_gate = self._read_bool_config(
            "setup_optimizer_execution_gate",
            "SETUP_OPTIMIZER_APPLY_TO_EXECUTION",
            True,
        )
        self._setup_optimizer_gate_ttl_s = self._read_float_config(
            "setup_optimizer_gate_ttl_s",
            "SETUP_OPTIMIZER_EXECUTION_GATE_TTL_SECONDS",
            60.0,
            1.0,
            3600.0,
        )
        self._setup_optimizer_gate_cache: tuple[float, bool, str, dict[str, Any]] = (
            0.0,
            False,
            "cold_start",
            {},
        )
        self._paper_execution_router_enabled = self._read_bool_config(
            "paper_execution_router_enabled",
            "PAPER_EXECUTION_ROUTER_ENABLED",
            True,
        )
        self._paper_execution_block_pending = self._read_bool_config(
            "paper_execution_block_pending",
            "PAPER_EXECUTION_ROUTER_BLOCK_PENDING",
            True,
        )
        self._paper_execution_min_score = self._read_float_config(
            "paper_execution_min_score",
            "PAPER_EXECUTION_ROUTER_MIN_SCORE",
            70.0,
            0.0,
            100.0,
        )
        self._paper_execution_profile: Dict[str, Any] = {
            "enabled": self._paper_execution_router_enabled,
            "mode": "paper_only",
            "active_variant": "grid_registry_default",
            "status": "startup",
            "last_reason": "not_evaluated",
            "last_action_at": None,
            "pending_variant": None,
            "applied_count": 0,
        }
        self._kelly_zero_fallback_mult = self._read_float_config(
            "kelly_zero_fallback_mult",
            "GRID_KELLY_ZERO_FALLBACK_MULT",
            0.25,
            0.0,
            1.0,
        )
        self.trailing_stops: Dict[int, TrailingStopATR] = {}
        self._atr_tracker = ATRFilter(period=14)

        self.grid_levels: List[float] = []
        self._runtime_capital_per_level: float = 0.0
        self._spec_cache: Optional[SpeculativeOrderCache] = None
        self._grid_initialized = False

        # V3: Adaptive grid components
        self._pair_profile = None
        self._range_calculator: Optional[Any] = None
        self._grid_allocator = _DynamicGridAllocator if _DynamicGridAllocator else None
        self._adaptive_mode = False
        self._cold_path_counter = 0
        self._cold_path_interval = self.config.get("adaptive_update_interval", 30) # Hetzner optimized

        # V3: Initialize adaptive components if profile available
        self._init_adaptive()

        # Only init grid now if center_price was explicitly provided
        if self.center_price is not None:
            self._init_grid()
            self._grid_initialized = True

        # Modules
        self._regime_detector = _RegimeDetector() if _RegimeDetector else None
        self._funding_monitor = _FundingRatesMonitor() if _FundingRatesMonitor else None
        self._oi_monitor = _OpenInterestMonitor() if _OpenInterestMonitor else None
        self._kelly = _KellyCriterion() if _KellyCriterion else None

        self.open_levels: Dict[int, Dict] = {}

        grid_step = self.range_percent / (self.num_levels - 1) if self.num_levels > 1 else 0.5
        self._sell_threshold_pct = max(1.5, grid_step * 0.8)
        self._entry_touch_bps = self._read_float_config(
            "entry_touch_bps",
            "GRID_ENTRY_TOUCH_BPS",
            15.0,
            0.0,
            500.0,
        )
        self._max_drawdown_pct = self.config.get("max_drawdown_pct", 10.0)
        self._grid_invalidation_factor = self.config.get("grid_invalidation_factor", 2.0)
        self._emergency_close_price = (
            self.center_price * (1 - self.range_percent * self._grid_invalidation_factor / 100)
            if self.center_price is not None else 0.0
        )

        self._price_history: deque = deque(maxlen=100)
        self._initialized = True
        self._emergency_mode = False

        # DGT — V3 SmartRecentering or legacy DGT
        self._dgt: Optional[Any] = None
        if self.config.get("enable_dgt", True) and self.center_price is not None:
            self._init_recentering()

        if self.center_price is not None:
            mode_str = "ADAPTIVE" if self._adaptive_mode else "FIXED"
            logger.info(
                f"GridAsync [{mode_str}]: {self.num_levels} niveaux, "
                f"+/-{self.range_percent:.1f}% sur {self.center_price:.0f}"
            )
        else:
            logger.info(
                f"GridAsync: {self.num_levels} niveaux, +/-{self.range_percent}% "
                f"— center_price sera initialise au premier prix recu"
            )

    def _read_float_config(
        self,
        config_key: str,
        env_key: str,
        default: float,
        minimum: float,
        maximum: float,
    ) -> float:
        raw = self.config.get(config_key, os.getenv(env_key, default))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _read_bool_config(self, config_key: str, env_key: str, default: bool) -> bool:
        raw = self.config.get(config_key, os.getenv(env_key, default))
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    # ------------------------------------------------------------------
    # V3: Initialization helpers
    # ------------------------------------------------------------------

    def _init_adaptive(self) -> None:
        """Initialize V3 adaptive components from config or registry."""
        symbol = getattr(self.instance.config, "symbol", None)
        if not symbol:
            return

        profile = self.config.get("pair_profile")
        if profile is None and _PairProfileRegistry is not None:
            from .adaptive_grid_config import get_default_registry
            registry = get_default_registry()
            if registry.has(symbol):
                profile = registry.get(symbol)

        if profile is None:
            return

        self._pair_profile = profile
        self._adaptive_mode = True
        self.range_percent = profile.base_range_pct
        self.num_levels = profile.base_num_levels
        self.max_capital_per_level = profile.max_capital_per_level

        if _AdaptiveRangeCalculator is not None:
            self._range_calculator = _AdaptiveRangeCalculator(profile)

        logger.info(
            "GridAsync V3 ADAPTIVE: %s — range=%.1f%% [%.1f-%.1f%%], "
            "levels=%d [%d-%d]",
            symbol, profile.base_range_pct, profile.min_range_pct,
            profile.max_range_pct, profile.base_num_levels,
            profile.min_levels, profile.max_levels,
        )

    def _init_recentering(self) -> None:
        """Initialize recentering (V3 SmartRecentering or legacy DGT)."""
        if self._adaptive_mode and _SmartRecentering is not None:
            self._dgt = _SmartRecentering(
                center_price=self.center_price,
                range_percent=self.range_percent,
                num_levels=self.num_levels,
                drift_threshold_pct=self.config.get("dgt_drift_threshold_pct", 5.0),
                adx_threshold=self.config.get("dgt_adx_threshold", 25.0),
                cooldown_minutes=self.config.get("dgt_cooldown_minutes", 45),
                max_recenters_per_day=self.config.get("dgt_max_recenters_per_day", 4),
                trailing_pct=self.config.get("dgt_trailing_pct", 5.0),
                min_shift_pct=self.config.get("dgt_min_shift_pct", 25.0),
                max_shift_pct=self.config.get("dgt_max_shift_pct", 75.0),
            )
            logger.info("GridAsync: SmartRecentering (V3) active")
        elif _GridRecenteringManager is not None:
            self._dgt = _GridRecenteringManager(
                center_price=self.center_price,
                range_percent=self.range_percent,
                num_levels=self.num_levels,
                drift_threshold_pct=self.config.get("dgt_drift_threshold_pct", 7.0),
                adx_threshold=self.config.get("dgt_adx_threshold", 25.0),
                cooldown_minutes=self.config.get("dgt_cooldown_minutes", 60),
                max_recenters_per_day=self.config.get("dgt_max_recenters_per_day", 3),
                trailing_pct=self.config.get("dgt_trailing_pct", 5.0),
            )

    # ------------------------------------------------------------------
    # Grid init
    # ------------------------------------------------------------------

    def _init_grid(self) -> None:
        self.grid_levels = calculate_grid_levels(
            center_price=self.center_price,
            range_percent=self.range_percent,
            num_levels=self.num_levels,
        )
        
        # P1: Liquidation Magnet (Task #38)
        # On ajuste légèrement les niveaux pour "coller" aux zones de liquidation probables.
        try:
            heatmap = self.instance.orchestrator.module_manager.get("liquidation_heatmap")
            if heatmap:
                zones = heatmap.get_liquidation_zones(self.center_price, top_n=3)
                for zone in zones:
                    z_price = zone["price"]
                    # Trouver le niveau de grille le plus proche
                    for i, level in enumerate(self.grid_levels):
                        # Si un niveau est à moins de 0.2% d'une zone de liquidation, on l'aligne pile dessus.
                        if abs(level - z_price) / z_price < 0.002:
                            logger.info(f"🧲 Liquidation Magnet: alignement niveau {i} sur {z_price}")
                            self.grid_levels[i] = z_price
        except Exception as exc:
            logger.debug(f"Liquidation Magnet skip: {exc}")

        available = self.instance.get_available_capital()

        if available <= 0:
            self._runtime_capital_per_level = 0.0
            logger.info(
                "Grid BUY paused for %s: capital disponible %.2f",
                getattr(self.instance.config, "symbol", "UNKNOWN"),
                available,
            )
            return

        max_buys = max(1, self.max_positions)
        min_required = max_buys * 5.0 / 0.90
        if available < min_required:
            self._runtime_capital_per_level = 0.0
            logger.info(
                "Grid BUY paused for %s: capital disponible %.2f < %.2f",
                getattr(self.instance.config, "symbol", "UNKNOWN"),
                available,
                min_required,
            )
            return

        # V3: Use DynamicGridAllocator if in adaptive mode
        if self._adaptive_mode and self._grid_allocator and self._pair_profile:
            atr_pct = self._get_atr_pct()
            self._runtime_capital_per_level = self._grid_allocator.compute_capital_per_level(
                self._pair_profile, available, self.num_levels, max_buys, atr_pct,
            )
        else:
            usable = available * 0.90
            dynamic = usable / max_buys
            self._runtime_capital_per_level = max(5.0, min(dynamic, self.max_capital_per_level))

        if self._spec_cache is not None:
            self._precompute_speculative_templates()

    def _get_atr_pct(self) -> Optional[float]:
        """Get current ATR% from ATRFilter if available. O(1)."""
        try:
            if hasattr(self.instance, "_atr_filter"):
                return self.instance._atr_filter.get_current_atr()
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # V3: Cold-path adaptive grid update
    # ------------------------------------------------------------------

    def _maybe_update_adaptive(self, price: float) -> None:
        """Cold-path: periodically recompute range and levels.

        Called every N ticks (default 60). NOT on every tick.
        """
        if not self._adaptive_mode or self._range_calculator is None:
            return

        self._cold_path_counter += 1
        if self._cold_path_counter < self._cold_path_interval:
            return
        self._cold_path_counter = 0

        atr_pct = self._get_atr_pct()
        new_range = self._range_calculator.update(atr_pct)

        # Only rebuild grid if range changed significantly (> 0.5%)
        if abs(new_range - self.range_percent) < 0.5:
            return

        old_range = self.range_percent
        self.range_percent = new_range

        if self._grid_allocator and self._pair_profile:
            self.num_levels = self._grid_allocator.compute_num_levels(
                self._pair_profile, atr_pct,
            )

        self.grid_levels = calculate_grid_levels(
            center_price=self.center_price,
            range_percent=self.range_percent,
            num_levels=self.num_levels,
        )

        grid_step = self.range_percent / (self.num_levels - 1) if self.num_levels > 1 else 0.5
        self._sell_threshold_pct = max(1.5, grid_step * 0.8)

        self._emergency_close_price = self.center_price * (
            1 - self.range_percent * self._grid_invalidation_factor / 100
        )

        available = self.instance.get_available_capital()
        if available > 0 and self._pair_profile and self._grid_allocator:
            max_buys = max(1, self.max_positions)
            self._runtime_capital_per_level = self._grid_allocator.compute_capital_per_level(
                self._pair_profile, available, self.num_levels, max_buys, atr_pct,
            )

        # Update DGT range
        if self._dgt:
            self._dgt.range_percent = new_range
            self._dgt.num_levels = self.num_levels

        if self._spec_cache is not None:
            self._precompute_speculative_templates()

        logger.info(
            "GridAsync ADAPTIVE update: range %.1f%% -> %.1f%%, levels %d",
            old_range, new_range, self.num_levels,
        )

    # ------------------------------------------------------------------
    # P6 — Speculative execution
    # ------------------------------------------------------------------

    def attach_speculative_cache(self, cache: SpeculativeOrderCache) -> None:
        self._spec_cache = cache
        self._precompute_speculative_templates()

    def _precompute_speculative_templates(self) -> None:
        if self._spec_cache is None:
            return
        symbol = self.instance.config.symbol
        self._spec_cache.invalidate_symbol(symbol)
        self._spec_cache.precompute_grid_levels(
            symbol=symbol,
            grid_levels=self.grid_levels,
            capital_per_level=self._runtime_capital_per_level,
        )
        logger.debug(
            "GridAsync P6: %d templates BUY pre-calcules pour %s",
            len(self.grid_levels), symbol,
        )

    def _find_nearest_level(self, price: float) -> int:
        if not self.grid_levels:
            return -1
        nearest_idx = 0
        min_dist = abs(price - self.grid_levels[0])
        for i, level in enumerate(self.grid_levels):
            d = abs(price - level)
            if d < min_dist:
                min_dist = d
                nearest_idx = i
        return nearest_idx

    def _get_buy_levels(self, current_price: float) -> List[int]:
        nearest = self._find_nearest_level(current_price)
        if nearest < 0:
            return []
        return [i for i in range(nearest) if i not in self.open_levels]

    def _sync_open_levels_from_instance_positions(self) -> None:
        if not self.grid_levels or not hasattr(self.instance, "get_positions_snapshot"):
            return
        try:
            positions = self.instance.get_positions_snapshot()
        except Exception:
            return
        for pos in positions:
            if pos.get("status") != "open":
                continue
            try:
                entry_price = float(pos.get("entry_price") or pos.get("buy_price") or 0.0)
                volume = float(pos.get("volume") or 0.0)
            except (TypeError, ValueError):
                continue
            if entry_price <= 0.0 or volume <= 0.0:
                continue
            idx = self._find_nearest_level(entry_price)
            if idx < 0:
                continue
            existing = self.open_levels.get(idx)
            if existing:
                old_volume = float(existing.get("volume", 0.0) or 0.0)
                total_volume = old_volume + volume
                if total_volume > 0:
                    existing["entry_price"] = (
                        (float(existing.get("entry_price", entry_price)) * old_volume)
                        + (entry_price * volume)
                    ) / total_volume
                    existing["volume"] = total_volume
                continue
            self.open_levels[idx] = {
                "entry_price": entry_price,
                "volume": volume,
                "opened_at": pos.get("open_time") or datetime.now(timezone.utc),
                "recovered": True,
            }

    def _build_buy_edge_metadata(self, level_index: int, current_price: float) -> Dict[str, float | str | int]:
        level_price = self.grid_levels[level_index]
        target_price = level_price * (1 + self._sell_threshold_pct / 100.0)
        expected_move_bps = max(0.0, ((target_price - current_price) / current_price) * 10000.0)
        level_distance_bps = ((current_price - level_price) / current_price) * 10000.0
        atr_pct = self._atr_tracker.get_current_atr()
        atr_bps = (atr_pct * 100.0) if atr_pct is not None else None
        metadata: Dict[str, float | str | int] = {
            "level_index": level_index,
            "level_price": level_price,
            "strategy": "grid",
            "expected_move_bps": expected_move_bps,
            "grid_expected_move_source": "grid_target_price",
            "grid_target_price": target_price,
            "grid_sell_threshold_pct": self._sell_threshold_pct,
            "grid_entry_level_distance_bps": level_distance_bps,
            "grid_entry_touch_bps": self._entry_touch_bps,
        }
        if atr_bps is not None:
            metadata["atr_bps"] = atr_bps
        return metadata

    def _passes_entry_touch_filter(self, level_index: int, current_price: float) -> bool:
        if self._entry_touch_bps <= 0.0:
            return True
        level_price = self.grid_levels[level_index]
        max_entry_price = level_price * (1 + self._entry_touch_bps / 10000.0)
        if current_price <= max_entry_price:
            return True
        logger.info(
            "Grid BUY skip: price %.6f is %.2f bps above level %.6f (max %.2f bps)",
            current_price,
            ((current_price - level_price) / current_price) * 10000.0,
            level_price,
            self._entry_touch_bps,
        )
        return False

    def _get_sell_levels(self, current_price: float) -> List[int]:
        sells = []
        for idx in self.open_levels:
            if current_price > self.grid_levels[idx] * (1 + self._sell_threshold_pct / 100):
                sells.append(idx)
        return sells

    def _can_open_position(self, available_capital: float, price: float) -> bool:
        if len(self.open_levels) >= self.max_positions:
            return False
        blocked, reason = self._realized_health_blocks_entry()
        if blocked:
            logger.info(
                "Grid BUY paused for %s: realized health gate (%s)",
                getattr(self.instance.config, "symbol", "UNKNOWN"),
                reason,
            )
            return False
        blocked, reason, details = self._setup_optimizer_blocks_entry(current_price=price)
        if blocked:
            logger.info(
                "Grid BUY paused for %s: setup optimizer gate (%s, %s)",
                getattr(self.instance.config, "symbol", "UNKNOWN"),
                reason,
                details,
            )
            return False
        cpl = self._calculate_kelly_cpl(price)
        return cpl > 0 and available_capital >= cpl

    def _check_drawdown(self, price: float) -> Optional[int]:
        for idx, pos in self.open_levels.items():
            dd = (pos["entry_price"] - price) / pos["entry_price"] * 100
            if dd >= self._max_drawdown_pct:
                return idx
        return None

    def _is_grid_invalidated(self, price: float) -> bool:
        return price < self._emergency_close_price

    # ------------------------------------------------------------------
    # on_price — CPU-bound, no I/O
    # ------------------------------------------------------------------

    def _calculate_kelly_cpl(self, price: float) -> float:
        """Calcul du capital par niveau ajusté par Kelly + Voter Strength (PF Boost P2)."""
        base_cpl = float(self._runtime_capital_per_level or 0.0)
        if base_cpl <= 0.0:
            return 0.0
        if not self.kelly_active or self._kelly is None:
            return base_cpl

        try:
            # 1) Get instance metrics
            trades = list(getattr(self.instance, "_trades", []))
            wins = [t for t in trades if (t.profit or 0.0) > 0]
            losses = [t for t in trades if (t.profit or 0.0) < 0]
            total = len(trades)
            win_rate = (len(wins) / total) if total > 0 else 0.5
            avg_win = (sum((t.profit or 0.0) for t in wins) / len(wins)) if wins else 1.0
            avg_loss = (abs(sum((t.profit or 0.0) for t in losses)) / len(losses)) if losses else 1.0
            pf = self.instance.get_profit_factor_days(30)
            
            # 2) Kelly Position Sizing
            capital = self.instance.get_current_capital()
            kelly_size = self._kelly.calculate_position_size(
                win_rate=win_rate,
                avg_win=float(max(avg_win, 1e-8)),
                avg_loss=float(max(avg_loss, 1e-8)),
                current_capital=capital,
                current_pf=float(pf if pf != float("inf") else 2.0)
            )
            
            if kelly_size <= 0:
                if total <= 0:
                    return base_cpl * self._kelly_zero_fallback_mult
                return 0.0

            # 3) Voter Strength Weighting
            voter_mult = 1.0
            if hasattr(self.instance.orchestrator, "voter"):
                tally = self.instance.orchestrator.voter.tally()
                if tally["signal"] == "BUY":
                    if tally["strength"] == "strong": voter_mult = 1.2
                    elif tally["strength"] == "weak": voter_mult = 0.9
                elif tally["signal"] == "SELL":
                    voter_mult = 0.6
            
            # Distribution
            final_cpl = kelly_size * voter_mult / 5.0 
            return max(5.0, min(final_cpl, self.max_capital_per_level))

        except Exception as e:
            logger.error(f"Error in Kelly sizing: {e}")
            return base_cpl

    def _realized_health_blocks_entry(self) -> tuple[bool, str]:
        """Block new paper grid entries for pairs with poor realized health."""
        if not self._block_underperforming_health:
            return False, "disabled"
        try:
            orchestrator = getattr(self.instance, "orchestrator", None)
            if orchestrator is None or not getattr(orchestrator, "paper_mode", False):
                return False, "not_paper"
            from ..pair_strategy_health import PairStrategyHealthEngine, symbol_key

            engine = getattr(orchestrator, "pair_strategy_health_engine", None)
            if engine is None:
                engine = PairStrategyHealthEngine()
                setattr(orchestrator, "pair_strategy_health_engine", engine)
            persistence = getattr(orchestrator, "persistence", None)
            db_path = getattr(persistence, "db_path", "data/autobot_state.db")
            snapshot = engine.build_snapshot_from_state_db(db_path, paper_mode=True)
            by_symbol = snapshot.get("by_symbol", {}) if isinstance(snapshot, dict) else {}
            context = by_symbol.get(symbol_key(getattr(self.instance.config, "symbol", None)))
            if not isinstance(context, dict):
                return False, "no_health_context"
            status = str(context.get("status") or "").lower()
            closed = int(float(context.get("closed_trades") or 0))
            if status == "weak" and closed >= int(engine.config.min_closed_trades):
                return True, "pair_health_weak"
            if status == "underperforming" and closed >= int(engine.config.min_closed_trades):
                return True, "pair_health_underperforming"
            if status == "early_weak" and closed >= int(engine.config.early_weak_min_closed_trades):
                return True, "pair_health_early_weak"
        except Exception as exc:
            logger.debug("Grid health gate unavailable: %s", exc)
        return False, "ok"

    def _setup_optimizer_blocks_entry(self, current_price: Optional[float] = None) -> tuple[bool, str, dict[str, Any]]:
        """Use the paper setup optimizer as an execution gate for the current setup.

        The optimizer does not blame a market pair. It only blocks the currently
        running grid setup when realized paper evidence says that this setup should
        be paused or adjusted while shadow variants keep learning separately.
        """
        if not self._setup_optimizer_execution_gate:
            return False, "disabled", {}
        try:
            orchestrator = getattr(self.instance, "orchestrator", None)
            if orchestrator is None or not getattr(orchestrator, "paper_mode", False):
                return False, "not_paper", {}

            now = time.monotonic()
            cached_at, cached_blocked, cached_reason, cached_details = self._setup_optimizer_gate_cache
            if now - cached_at <= self._setup_optimizer_gate_ttl_s:
                return cached_blocked, cached_reason, dict(cached_details)

            from ..pair_strategy_health import PairStrategyHealthEngine, symbol_key
            from ..setup_optimizer import PairSetupOptimizer

            symbol = symbol_key(getattr(self.instance.config, "symbol", None))
            if not symbol or symbol == "UNKNOWN":
                return self._cache_setup_optimizer_gate(now, False, "unknown_symbol", {})

            optimizer = getattr(orchestrator, "setup_optimizer", None)
            if optimizer is None:
                optimizer = PairSetupOptimizer()
                setattr(orchestrator, "setup_optimizer", optimizer)
            if not getattr(optimizer.config, "enabled", True):
                return self._cache_setup_optimizer_gate(now, False, "optimizer_disabled", {})
            if not getattr(optimizer.config, "apply_to_execution", False):
                return self._cache_setup_optimizer_gate(now, False, "optimizer_observe_only", {})

            health_engine = getattr(orchestrator, "pair_strategy_health_engine", None)
            if health_engine is None:
                health_engine = PairStrategyHealthEngine()
                setattr(orchestrator, "pair_strategy_health_engine", health_engine)
            persistence = getattr(orchestrator, "persistence", None)
            db_path = getattr(persistence, "db_path", "data/autobot_state.db")
            health_snapshot = health_engine.build_snapshot_from_state_db(db_path, paper_mode=True)
            health = (health_snapshot.get("by_symbol", {}) if isinstance(health_snapshot, dict) else {}).get(symbol, {})

            shadow = {}
            shadow_lab = getattr(orchestrator, "setup_shadow_lab", None)
            if shadow_lab is not None and hasattr(shadow_lab, "evidence_by_symbol"):
                shadow = shadow_lab.evidence_by_symbol().get(symbol, {})

            plan = optimizer.analyze_symbol(
                symbol=symbol,
                instances=[
                    {
                        "symbol": symbol,
                        "strategy": "grid",
                        "range_percent": self.range_percent,
                        "num_levels": self.num_levels,
                        "max_capital_per_level": self.max_capital_per_level,
                    }
                ],
                opportunity={},
                health=health if isinstance(health, dict) else {},
                shadow=shadow if isinstance(shadow, dict) else {},
                paper_mode=True,
            )
            selected = plan.selected_variant.to_dict() if plan.selected_variant else {}
            paper_execution = self._maybe_promote_grid_shadow_candidate(
                plan=plan,
                selected=selected,
                current_price=current_price,
            )
            details = {
                "status": plan.status,
                "action": plan.recommended_action,
                "selected_variant": selected.get("name"),
                "selected_score": selected.get("score"),
                "health_status": (health or {}).get("status") if isinstance(health, dict) else None,
                "closed_trades": (health or {}).get("closed_trades") if isinstance(health, dict) else None,
                "net_pnl_eur": (health or {}).get("net_pnl_eur") if isinstance(health, dict) else None,
                "profit_factor": (health or {}).get("profit_factor") if isinstance(health, dict) else None,
                "paper_execution": paper_execution,
            }
            blocking_actions = {
                "paper_shadow_variant_outperforms_current_setup",
                "pause_current_setup_and_test_selected_variant_in_paper",
                "test_selected_variant_in_paper_shadow",
            }
            blocked = plan.status in {"pause_current", "adjust"} or plan.recommended_action in blocking_actions
            if paper_execution.get("block_new_entries"):
                blocked = True
            reason = f"{plan.status}:{plan.recommended_action}"
            return self._cache_setup_optimizer_gate(now, blocked, reason, details)
        except Exception as exc:
            logger.debug("Setup optimizer gate unavailable: %s", exc)
            return False, "unavailable", {"error": str(exc)}

    def _maybe_promote_grid_shadow_candidate(
        self,
        *,
        plan: Any,
        selected: Mapping[str, Any],
        current_price: Optional[float],
    ) -> dict[str, Any]:
        """Apply a proven shadow grid variant to official paper execution.

        This is deliberately paper-only and grid-only. Trend and mean-reversion
        shadow engines keep learning until they have enough closed-trade
        evidence and an execution adapter is explicitly added.
        """
        result: dict[str, Any] = {
            "enabled": self._paper_execution_router_enabled,
            "mode": "paper_only",
            "engine": "dynamic_grid",
            "action": "observe",
            "reason": "not_candidate",
            "block_new_entries": False,
            "selected_variant": selected.get("name"),
            "active_variant": self._paper_execution_profile.get("active_variant"),
        }
        if not self._paper_execution_router_enabled:
            result["reason"] = "paper_execution_router_disabled"
            self._remember_paper_execution(result)
            return result

        orchestrator = getattr(getattr(self, "instance", None), "orchestrator", None)
        paper_mode = bool(orchestrator and getattr(orchestrator, "paper_mode", False))
        if not paper_mode:
            result["reason"] = "not_paper_mode"
            self._remember_paper_execution(result)
            return result

        action = str(getattr(plan, "recommended_action", "") or "")
        status = str(getattr(plan, "status", "") or "")
        if status != "candidate" or action not in {"paper_shadow_candidate_review", "paper_review_selected_variant"}:
            result["reason"] = f"{status}:{action}" if status or action else "not_candidate"
            self._remember_paper_execution(result)
            return result

        score = self._safe_float(selected.get("score"), 0.0)
        if score < self._paper_execution_min_score:
            result["reason"] = "candidate_score_below_paper_execution_min"
            result["selected_score"] = score
            self._remember_paper_execution(result)
            return result

        grid_config = selected.get("grid_config")
        if not isinstance(grid_config, Mapping):
            result["reason"] = "selected_variant_has_no_grid_config"
            self._remember_paper_execution(result)
            return result

        open_count = len(getattr(self, "open_levels", {}) or {})
        if open_count > 0:
            result.update(
                {
                    "action": "defer_until_flat",
                    "reason": "open_positions_keep_current_grid_until_flat",
                    "open_levels": open_count,
                    "block_new_entries": self._paper_execution_block_pending,
                }
            )
            self._paper_execution_profile["pending_variant"] = selected.get("name")
            self._paper_execution_profile["pending_grid_config"] = dict(grid_config)
            self._remember_paper_execution(result)
            return result

        price = self._safe_float(current_price, self._safe_float(getattr(self, "center_price", 0.0), 0.0))
        if price <= 0.0 or not math.isfinite(price):
            result["reason"] = "current_price_unavailable"
            self._remember_paper_execution(result)
            return result

        if self._grid_config_matches_runtime(grid_config):
            result.update({"action": "already_active", "reason": "selected_grid_config_already_active"})
            self._paper_execution_profile["active_variant"] = selected.get("name") or self._paper_execution_profile.get("active_variant")
            self._remember_paper_execution(result)
            return result

        applied = self._apply_paper_grid_config(grid_config, price, selected.get("name"))
        result.update(applied)
        self._remember_paper_execution(result)
        return result

    def _apply_paper_grid_config(
        self,
        grid_config: Mapping[str, Any],
        current_price: float,
        variant_name: Any,
    ) -> dict[str, Any]:
        previous = {
            "range_percent": self.range_percent,
            "num_levels": self.num_levels,
            "max_capital_per_level": self.max_capital_per_level,
            "max_positions": self.max_positions,
            "entry_touch_bps": self._entry_touch_bps,
        }
        self.range_percent = self._safe_float(grid_config.get("range_percent"), self.range_percent)
        self.num_levels = max(2, int(self._safe_float(grid_config.get("num_levels"), self.num_levels)))
        self.max_capital_per_level = max(
            0.0,
            self._safe_float(grid_config.get("max_capital_per_level"), self.max_capital_per_level),
        )
        self.max_positions = max(1, int(self._safe_float(grid_config.get("max_positions"), self.max_positions)))
        self._entry_touch_bps = max(0.0, self._safe_float(grid_config.get("entry_touch_bps"), self._entry_touch_bps))

        grid_step = self.range_percent / (self.num_levels - 1) if self.num_levels > 1 else 0.5
        self._sell_threshold_pct = max(1.5, grid_step * 0.8)
        self.center_price = current_price
        self._init_grid()
        self._grid_initialized = True
        self._emergency_mode = False
        self._emergency_close_price = self.center_price * (
            1 - self.range_percent * self._grid_invalidation_factor / 100
        )
        self.trailing_stops.clear()
        if self._dgt is not None:
            self._dgt = None
            if self.config.get("enable_dgt", True):
                self._init_recentering()
        if self._spec_cache is not None:
            self._precompute_speculative_templates()

        self._paper_execution_profile["active_variant"] = str(variant_name or "dynamic_grid_candidate")
        self._paper_execution_profile["applied_count"] = int(self._paper_execution_profile.get("applied_count") or 0) + 1
        logger.info(
            "Paper execution router applied %s to %s: range=%.3f%% levels=%d max_cpl=%.2f max_pos=%d entry_touch=%.2f",
            variant_name,
            getattr(self.instance.config, "symbol", "UNKNOWN"),
            self.range_percent,
            self.num_levels,
            self.max_capital_per_level,
            self.max_positions,
            self._entry_touch_bps,
        )
        return {
            "action": "applied",
            "reason": "shadow_candidate_promoted_to_official_paper_grid",
            "previous_grid_config": previous,
            "applied_grid_config": {
                "range_percent": self.range_percent,
                "num_levels": self.num_levels,
                "max_capital_per_level": self.max_capital_per_level,
                "max_positions": self.max_positions,
                "entry_touch_bps": self._entry_touch_bps,
                "sell_threshold_pct": self._sell_threshold_pct,
            },
            "active_variant": self._paper_execution_profile["active_variant"],
            "block_new_entries": False,
        }

    def _grid_config_matches_runtime(self, grid_config: Mapping[str, Any]) -> bool:
        expected = {
            "range_percent": self._safe_float(grid_config.get("range_percent"), self.range_percent),
            "num_levels": int(self._safe_float(grid_config.get("num_levels"), self.num_levels)),
            "max_capital_per_level": self._safe_float(grid_config.get("max_capital_per_level"), self.max_capital_per_level),
            "max_positions": int(self._safe_float(grid_config.get("max_positions"), self.max_positions)),
            "entry_touch_bps": self._safe_float(grid_config.get("entry_touch_bps"), self._entry_touch_bps),
        }
        actual = {
            "range_percent": self.range_percent,
            "num_levels": self.num_levels,
            "max_capital_per_level": self.max_capital_per_level,
            "max_positions": self.max_positions,
            "entry_touch_bps": self._entry_touch_bps,
        }
        return all(abs(float(actual[key]) - float(expected[key])) < 1e-9 for key in actual)

    def _remember_paper_execution(self, result: Mapping[str, Any]) -> None:
        self._paper_execution_profile.update(
            {
                "enabled": self._paper_execution_router_enabled,
                "status": result.get("action", "observe"),
                "last_reason": result.get("reason"),
                "last_action_at": datetime.now(timezone.utc).isoformat(),
                "selected_variant": result.get("selected_variant"),
                "active_variant": result.get("active_variant", self._paper_execution_profile.get("active_variant")),
                "block_new_entries": bool(result.get("block_new_entries", False)),
            }
        )

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _cache_setup_optimizer_gate(
        self,
        timestamp: float,
        blocked: bool,
        reason: str,
        details: dict[str, Any],
    ) -> tuple[bool, str, dict[str, Any]]:
        self._setup_optimizer_gate_cache = (timestamp, blocked, reason, dict(details))
        return blocked, reason, details

    def _get_active_trailing_sells(self, current_price: float, symbol: str) -> List[int]:
        """Gère la logique de Trailing Take-Profit (Phase 3)."""
        if not self.trailing_tp_active:
            return self._get_sell_levels(current_price)
            
        ready_to_sell = []
        current_atr_pct = self._atr_tracker.get_current_atr()
        
        if not current_atr_pct:
            return self._get_sell_levels(current_price)
            
        atr_val = (current_atr_pct / 100) * current_price
        
        for idx, pos in list(self.open_levels.items()):
            lp = self.grid_levels[idx]
            target_price = lp * (1 + self._sell_threshold_pct / 100)
            
            if current_price >= target_price:
                if idx not in self.trailing_stops:
                    self.trailing_stops[idx] = TrailingStopATR(atr_multiplier=1.5, activation_profit=0.5)
                
                stop_price = self.trailing_stops[idx].update(current_price, atr_val, target_price)
                
                if current_price < stop_price:
                    logger.info(f"📈 Trailing TP déclenché pour {symbol} niveau {idx} (stop @ {stop_price:.2f})")
                    ready_to_sell.append(idx)
                    self.trailing_stops.pop(idx, None)
            else:
                self.trailing_stops.pop(idx, None)
                
        return ready_to_sell

    def on_price(self, price: float) -> None:
        # Update volatility tracker
        self._atr_tracker.on_price(price)

        if not self._initialized or not math.isfinite(price) or price <= 0:
            return

        # V3: Feed price to range calculator (O(1) deque append)
        if self._range_calculator is not None:
            self._range_calculator.on_price(price)
            
        # Phase 6: Update RegimeDetector (simulated OHLC from tick)
        if self._regime_detector:
            self._regime_detector.update(high=price, low=price, close=price)

        # Dynamic grid initialization on first price received
        if not self._grid_initialized:
            if self.center_price is None:
                self.center_price = price
                logger.info(f"Grid initialisee au prix: {price:.2f}")
            self._init_grid()
            self._grid_initialized = True
            self._sync_open_levels_from_instance_positions()

            if self._dgt is None and self.config.get("enable_dgt", True):
                self._init_recentering()

            self._emergency_close_price = self.center_price * (
                1 - self.range_percent * self._grid_invalidation_factor / 100
            )

            mode_str = "ADAPTIVE" if self._adaptive_mode else "FIXED"
            logger.info(
                f"GridAsync [{mode_str}]: {self.num_levels} niveaux, "
                f"+/-{self.range_percent:.1f}% sur {self.center_price:.0f}"
            )

        # Stale data check
        if hasattr(self.instance, "orchestrator") and self.instance.orchestrator:
            ws = self.instance.orchestrator.ws_client
            if hasattr(ws, "is_data_fresh") and not ws.is_data_fresh():
                return

        available_capital = self.instance.get_available_capital()
        self._price_history.append(price)
        symbol = self.instance.config.symbol

        # V3: Cold-path adaptive update (every N ticks)
        self._maybe_update_adaptive(price)

        # DGT — trailing anchor
        if self._dgt and not self._emergency_mode:
            self._dgt.check_trailing_anchor(price)

        # DGT — recenter check
        if self._dgt and not self._emergency_mode:
            adx: Optional[float] = None
            if self._regime_detector and hasattr(self._regime_detector, "get_adx"):
                adx = self._regime_detector.get_adx()

            if self._dgt.should_recenter(price, adx=adx):
                # V3 SmartRecentering: progressive shift, selective position close
                if self._adaptive_mode and hasattr(self._dgt, "compute_recenter"):
                    result = self._dgt.compute_recenter(
                        price, self.open_levels, self.grid_levels,
                    )
                    if result.should_recenter:
                        # Close only positions marked for closure
                        positions_closed = set()
                        for i, idx in enumerate(result.positions_to_close):
                            pos = self.open_levels.get(idx)
                            if pos:
                                sig = TradingSignal(
                                    type=SignalType.SELL,
                                    symbol=symbol, price=price,
                                    volume=pos["volume"],
                                    reason=f"SmartRecenter: closing OOB level {idx}",
                                    timestamp=datetime.now(timezone.utc),
                                    metadata={
                                        "level_index": idx,
                                        "smart_recenter": True,
                                        "strategy": "grid",
                                    },
                                )
                                self.emit_signal(sig, bypass_cooldown=(i > 0))
                                positions_closed.add(idx)

                        self.center_price = result.new_center
                        self.grid_levels = result.new_grid_levels
                        for idx in positions_closed:
                            self.open_levels.pop(idx, None)
                            self.trailing_stops.pop(idx, None)
                        self._emergency_close_price = self.center_price * (
                            1 - self.range_percent * self._grid_invalidation_factor / 100
                        )
                        if self._spec_cache is not None:
                            self._precompute_speculative_templates()
                        return
                else:
                    # Legacy DGT: close all positions, snap to price
                    for i, (idx, pos) in enumerate(list(self.open_levels.items())):
                        sig = TradingSignal(
                            type=SignalType.SELL,
                            symbol=symbol, price=price,
                            volume=pos["volume"],
                            reason=f"DGT: recentering — closing level {idx}",
                            timestamp=datetime.now(timezone.utc),
                            metadata={"level_index": idx, "dgt_recenter": True, "strategy": "grid"},
                        )
                        self.emit_signal(sig, bypass_cooldown=(i > 0))

                    result = self._dgt.recenter(price)
                    self.center_price = result.new_center
                    self.grid_levels = result.new_grid_levels
                    self.open_levels.clear()
                    self._emergency_close_price = self.center_price * (
                        1 - self.range_percent * self._grid_invalidation_factor / 100
                    )
                    if self._spec_cache is not None:
                        self._precompute_speculative_templates()
                    return

        # Emergency mode
        if not self._emergency_mode and self._is_grid_invalidated(price):
            self._emergency_mode = True
            logger.error(f"GRID INVALIDATED: {price:.0f} < {self._emergency_close_price:.0f}")

        if self._emergency_mode:
            for i, (idx, pos) in enumerate(list(self.open_levels.items())):
                sig = TradingSignal(
                    type=SignalType.SELL, symbol=symbol, price=price,
                    volume=pos["volume"],
                    reason=f"EMERGENCY: Grid invalidated - level {idx}",
                    timestamp=datetime.now(timezone.utc),
                    metadata={"level_index": idx, "emergency": True, "strategy": "grid"},
                )
                self.emit_signal(sig, bypass_cooldown=(i > 0))
            return

        # Drawdown check
        emergency_level = self._check_drawdown(price)
        if emergency_level is not None:
            pos = self.open_levels.get(emergency_level)
            if pos:
                sig = TradingSignal(
                    type=SignalType.SELL, symbol=symbol, price=price,
                    volume=pos["volume"],
                    reason=f"STOP-LOSS: Drawdown {self._max_drawdown_pct}% atteint",
                    timestamp=datetime.now(timezone.utc),
                    metadata={"level_index": emergency_level, "stop_loss": True, "strategy": "grid"},
                )
                self.emit_signal(sig)

        # Sells with Trailing TP (Phase 3)
        active_sells = self._get_active_trailing_sells(price, symbol)
        sell_data = [(idx, self.open_levels[idx], self.grid_levels[idx]) for idx in active_sells if idx in self.open_levels]
        for i, (idx, pos, lp) in enumerate(sell_data):
            pct = (price - lp) / lp * 100
            sig = TradingSignal(
                type=SignalType.SELL, symbol=symbol, price=price,
                volume=pos["volume"],
                reason=f"Grid level {idx} profit: +{pct:.2f}%",
                timestamp=datetime.now(timezone.utc),
                metadata={"level_index": idx, "level_price": lp, "entry_price": pos["entry_price"], "strategy": "grid"},
            )
            self.emit_signal(sig, bypass_cooldown=(i > 0))

        # Module checks
        if self._regime_detector and not self._regime_detector.should_trade_grid():
            return
        if self._oi_monitor and self._oi_monitor.is_squeeze_risk():
            return

        # PF Boost: Voter Entry Filter
        if self.voter_filter_active and hasattr(self.instance.orchestrator, "voter"):
            tally = self.instance.orchestrator.voter.tally()
            if tally["signal"] == "SELL" and tally["strength"] == "strong":
                # Pour une grille LONG (achat de baisse), on évite d'acheter si le consensus est fortement baissier
                logger.warning(f"🛡️ Voter Filter: skip BUY for {symbol} (consensus: STRONG SELL)")
                return

        # Buys
        if self._can_open_position(available_capital, price):
            buy_levels = self._get_buy_levels(price)
            if buy_levels:
                best = max(buy_levels)
                if not self._passes_entry_touch_filter(best, price):
                    return
                # Kelly Dynamic Sizing (Phase 2)
                cpl = self._calculate_kelly_cpl(price)
                if cpl > 0:
                    volume = cpl / price
                    metadata = self._build_buy_edge_metadata(best, price)
                    sig = TradingSignal(
                        type=SignalType.BUY, symbol=symbol, price=price,
                        volume=volume,
                        reason=f"Grid buy level {best} @ {self.grid_levels[best]:.0f}",
                        timestamp=datetime.now(timezone.utc),
                        metadata=metadata,
                    )
                    self.emit_signal(sig)

    def on_position_opened(self, position: Any) -> None:
        if not hasattr(position, "buy_price"):
            return
        idx = self._find_nearest_level(position.buy_price)
        if idx >= 0:
            self.open_levels[idx] = {
                "entry_price": position.buy_price,
                "volume": position.volume,
                "opened_at": datetime.now(timezone.utc),
            }
            if self._spec_cache is not None:
                symbol = self.instance.config.symbol
                self._spec_cache.store_sell_template(
                    symbol=symbol,
                    level_index=idx,
                    level_price=self.grid_levels[idx] if idx < len(self.grid_levels) else position.buy_price,
                    volume=position.volume,
                )

    def on_position_closed(self, position: Any, profit: float) -> None:
        if not hasattr(position, "buy_price"):
            return
        idx = self._find_nearest_level(position.buy_price)
        self.open_levels.pop(idx, None)
        self.trailing_stops.pop(idx, None)
        if self._spec_cache is not None:
            symbol = self.instance.config.symbol
            self._spec_cache.invalidate(symbol, "sell", idx)

    def reset(self) -> None:
        self.open_levels.clear()
        self._price_history.clear()
        self._emergency_mode = False
        self._cold_path_counter = 0
        super().reset()

    # ------------------------------------------------------------------
    # V3: Status with adaptive info
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        status.update({
            "adaptive_mode": self._adaptive_mode,
            "range_percent": self.range_percent,
            "num_levels": self.num_levels,
            "center_price": self.center_price,
            "open_levels_count": len(self.open_levels),
            "capital_per_level": self._runtime_capital_per_level,
            "grid_initialized": self._grid_initialized,
            "emergency_mode": self._emergency_mode,
            "paper_execution_router": dict(self._paper_execution_profile),
        })
        if self._range_calculator:
            status["range_calculator"] = self._range_calculator.get_status()
        if self._dgt and hasattr(self._dgt, "get_status"):
            status["recentering"] = self._dgt.get_status()
        if self._pair_profile:
            status["pair_profile"] = self._pair_profile.symbol
        return status
