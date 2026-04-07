"""
MultiGridOrchestrator — Manage multiple grids per pair (short-term + long-term).

Allows running two complementary grids on the same pair:
- **Short-term grid**: Tight range, many levels, captures micro-movements.
- **Long-term grid**: Wide range, fewer levels, captures macro-swings.

Each sub-grid is an independent GridStrategyAsync instance with its own
config, state, and speculative cache.  The orchestrator routes price ticks
to all sub-grids and aggregates signals.

Capital allocation between sub-grids is configurable (default: 60% short / 40% long).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from . import TradingSignal
from .adaptive_grid_config import PairProfile

__all__ = ["MultiGridOrchestrator", "SubGridConfig"]

logger = logging.getLogger(__name__)


@dataclass
class SubGridConfig:
    """Configuration for a sub-grid within a multi-grid setup.

    Attributes:
        name:               Human-readable name (e.g. "short-term", "long-term").
        range_multiplier:   Multiplied by the adaptive range to get this grid's range.
                            e.g. 0.5 for short-term (half the adaptive range),
                            2.0 for long-term (double the adaptive range).
        level_multiplier:   Multiplied by the adaptive num_levels.
                            e.g. 1.5 for short-term (more levels), 0.6 for long-term.
        capital_share:      Fraction of total capital allocated to this grid [0, 1].
        max_positions:      Max open positions for this sub-grid.
    """

    name: str = "default"
    range_multiplier: float = 1.0
    level_multiplier: float = 1.0
    capital_share: float = 1.0
    max_positions: int = 10


# Pre-defined multi-grid configurations
SHORT_TERM_CONFIG = SubGridConfig(
    name="short-term",
    range_multiplier=0.5,
    level_multiplier=1.3,
    capital_share=0.60,
    max_positions=8,
)

LONG_TERM_CONFIG = SubGridConfig(
    name="long-term",
    range_multiplier=2.0,
    level_multiplier=0.6,
    capital_share=0.40,
    max_positions=5,
)

DEFAULT_MULTI_GRID = [SHORT_TERM_CONFIG, LONG_TERM_CONFIG]


class MultiGridOrchestrator:
    """Orchestrates multiple grids for a single pair.

    This class does NOT own GridStrategyAsync instances directly (to avoid
    circular imports).  Instead, it:
    1. Computes per-sub-grid configs (range, levels, capital).
    2. Routes price ticks to all sub-grids.
    3. Aggregates signals with proper tagging.

    Usage:
        orchestrator = MultiGridOrchestrator(profile, sub_grids=DEFAULT_MULTI_GRID)

        # Get config for each sub-grid to pass to GridStrategyAsync
        configs = orchestrator.get_sub_grid_configs(
            base_range_pct=5.0,
            base_num_levels=15,
            total_capital=1000.0,
        )
        # configs[0] = {"range_percent": 2.5, "num_levels": 20, "max_capital_per_level": ..., ...}
        # configs[1] = {"range_percent": 10.0, "num_levels": 9, "max_capital_per_level": ..., ...}
    """

    def __init__(
        self,
        profile: PairProfile,
        sub_grids: Optional[List[SubGridConfig]] = None,
    ) -> None:
        self._profile = profile
        self._sub_grids = sub_grids or DEFAULT_MULTI_GRID

        # Validate capital shares sum to ~1.0
        total_share = sum(sg.capital_share for sg in self._sub_grids)
        if abs(total_share - 1.0) > 0.01:
            logger.warning(
                "MultiGrid %s: capital shares sum to %.2f (expected 1.0), normalising",
                profile.symbol,
                total_share,
            )
            # Normalise
            for sg in self._sub_grids:
                object.__setattr__(sg, "capital_share", sg.capital_share / total_share)

        self._strategies: Dict[str, Any] = {}  # name -> GridStrategyAsync
        self._signal_callback: Optional[Callable] = None

        logger.info(
            "MultiGridOrchestrator: %s — %d sub-grids (%s)",
            profile.symbol,
            len(self._sub_grids),
            ", ".join(sg.name for sg in self._sub_grids),
        )

    @property
    def sub_grid_count(self) -> int:
        return len(self._sub_grids)

    @property
    def sub_grid_names(self) -> List[str]:
        return [sg.name for sg in self._sub_grids]

    def get_sub_grid_configs(
        self,
        base_range_pct: float,
        base_num_levels: int,
        total_capital: float,
        base_max_capital_per_level: float = 50.0,
    ) -> List[Dict[str, Any]]:
        """Compute the configuration dict for each sub-grid.

        These dicts can be passed directly to GridStrategyAsync as the
        ``config`` parameter.

        Args:
            base_range_pct:             The adaptive range (from AdaptiveRangeCalculator).
            base_num_levels:            The adaptive number of levels.
            total_capital:              Total capital available for this pair.
            base_max_capital_per_level: Base max capital per level.

        Returns:
            List of config dicts, one per sub-grid, in the same order as
            ``self._sub_grids``.
        """
        configs = []
        for sg in self._sub_grids:
            range_pct = max(
                self._profile.min_range_pct,
                min(self._profile.max_range_pct, base_range_pct * sg.range_multiplier),
            )
            num_levels = max(
                self._profile.min_levels,
                min(
                    self._profile.max_levels,
                    int(round(base_num_levels * sg.level_multiplier)),
                ),
            )
            allocated_capital = total_capital * sg.capital_share
            max_cpl = base_max_capital_per_level * sg.capital_share

            configs.append({
                "range_percent": round(range_pct, 2),
                "num_levels": num_levels,
                "max_capital_per_level": round(max_cpl, 2),
                "max_positions": sg.max_positions,
                "sub_grid_name": sg.name,
                "capital_share": sg.capital_share,
                "allocated_capital": round(allocated_capital, 2),
            })

        return configs

    # ------------------------------------------------------------------
    # Strategy management
    # ------------------------------------------------------------------

    def register_strategy(self, name: str, strategy: Any) -> None:
        """Register a GridStrategyAsync instance for a sub-grid."""
        self._strategies[name] = strategy
        logger.debug("MultiGrid: registered strategy for sub-grid '%s'", name)

    def on_price(self, price: float) -> None:
        """Route a price tick to all registered sub-grid strategies.

        O(K) where K = number of sub-grids (typically 2).
        """
        for name, strategy in self._strategies.items():
            try:
                strategy.on_price(price)
            except Exception as exc:
                logger.error(
                    "MultiGrid: error in sub-grid '%s' on_price: %s",
                    name,
                    exc,
                    exc_info=True,
                )

    def on_position_opened(self, position: Any) -> None:
        """Notify all sub-grids of a position opened."""
        for strategy in self._strategies.values():
            try:
                strategy.on_position_opened(position)
            except Exception:
                pass

    def on_position_closed(self, position: Any, profit: float) -> None:
        """Notify all sub-grids of a position closed."""
        for strategy in self._strategies.values():
            try:
                strategy.on_position_closed(position, profit)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        return {
            "symbol": self._profile.symbol,
            "sub_grid_count": len(self._sub_grids),
            "sub_grids": [
                {
                    "name": sg.name,
                    "range_multiplier": sg.range_multiplier,
                    "level_multiplier": sg.level_multiplier,
                    "capital_share": sg.capital_share,
                    "max_positions": sg.max_positions,
                    "strategy_registered": sg.name in self._strategies,
                }
                for sg in self._sub_grids
            ],
        }
