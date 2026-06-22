"""Observation-only strategy used while execution strategies are retired.

This class deliberately consumes market ticks without emitting a trading
signal. It keeps watched instances and market-data observability alive while
research determines whether another strategy deserves a controlled paper run.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from .strategy_async import StrategyAsync


class ObservationOnlyStrategyAsync(StrategyAsync):
    """A no-op runtime strategy with explicit, inspectable state."""

    def __init__(self, instance: Any, config: Optional[Dict] = None) -> None:
        super().__init__(instance, config)
        self._initialized = True
        self._last_price: float | None = None
        self._tick_count = 0

    def on_price(self, price: float) -> None:
        if not math.isfinite(price) or price <= 0.0:
            return
        self._last_price = float(price)
        self._tick_count += 1

    def on_position_opened(self, position: Any) -> None:
        return None

    def on_position_closed(self, position: Any, profit: float) -> None:
        return None

    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        status.update(
            {
                "mode": "observation_only",
                "execution_enabled": False,
                "signal_emission_enabled": False,
                "reason": "grid_retired_research_only",
                "tick_count": self._tick_count,
                "last_price": self._last_price,
            }
        )
        return status
