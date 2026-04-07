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
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import TradingSignal, SignalType, calculate_grid_levels, PositionSizing
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
        self.range_percent = self.config.get("range_percent", 7.0)
        self.num_levels = self.config.get("num_levels", 15)
        self.max_capital_per_level = self.config.get("max_capital_per_level", 50.0)
        self.max_positions = self.config.get("max_positions", 10)

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
        self._cold_path_interval = self.config.get("adaptive_update_interval", 60)

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
        available = self.instance.get_available_capital()
        if available <= 0:
            raise ValueError(f"Capital invalide: {available:.2f}")

        max_buys = max(1, self.max_positions)

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

        min_required = max_buys * 5.0 / 0.90
        if available < min_required:
            raise ValueError(f"Capital insuffisant: {available:.2f} < {min_required:.2f}")

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

    def attach_speculative_cache(self, cache: SpeculativeOrderCache)