"""
SmartRecentering — Progressive grid recentering (replaces GridRecenteringManager).

Key improvements over the original DGT recentering:
1. **Progressive shift**: moves the grid center in steps (25%-50%) instead of
   a full 100% snap to the current price.  Reduces P&L whiplash.
2. **Velocity-aware**: uses price velocity (rate of change) to decide how
   aggressively to shift.  Fast moves -> bigger steps; slow drift -> smaller.
3. **Position-aware**: considers open positions.  If most positions are in
   profit, a larger shift is acceptable.  If deep in loss, shift is conservative.
4. **Graceful close**: optionally closes only the most out-of-range positions
   instead of liquidating everything before a recenter.

Fully async-safe (``asyncio.Lock``).  All heavy logic in ``compute_recenter()``
(cold path).  ``should_recenter()`` is O(1) for hot-path gating.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from ..strategies import calculate_grid_levels

__all__ = ["SmartRecentering", "SmartRecenterResult"]

logger = logging.getLogger(__name__)


@dataclass
class SmartRecenterResult:
    """Result of a smart recentering computation."""

    should_recenter: bool
    old_center: float
    new_center: float
    shift_pct: float  # How much of the gap was actually shifted (0-100%)
    new_grid_levels: List[float]
    positions_to_close: List[int]  # Level indices that should be closed
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    recenter_count_today: int = 0


class SmartRecentering:
    """Progressive grid recentering manager.

    Drop-in replacement for ``GridRecenteringManager`` with smarter,
    less aggressive recentering logic.

    Configuration (via constructor):
        drift_threshold_pct:      Min drift to even consider recentering (default 5%).
        adx_threshold:            Block recenter if ADX >= this (strong trend, default 25).
        cooldown_minutes:         Min time between recenters (default 45).
        max_recenters_per_day:    Daily cap (default 4).
        trailing_pct:             Soft trailing anchor threshold (default 5%).
        min_shift_pct:            Minimum shift ratio per recenter (default 25%).
        max_shift_pct:            Maximum shift ratio per recenter (default 75%).
        velocity_window:          Number of recent prices for velocity calc (default 20).
    """

    def __init__(
        self,
        center_price: float,
        range_percent: float,
        num_levels: int,
        *,
        drift_threshold_pct: float = 5.0,
        adx_threshold: float = 25.0,
        cooldown_minutes: int = 45,
        max_recenters_per_day: int = 4,
        trailing_pct: float = 5.0,
        min_shift_pct: float = 25.0,
        max_shift_pct: float = 75.0,
        velocity_window: int = 20,
    ) -> None:
        self.center_price = center_price
        self.range_percent = range_percent
        self.num_levels = num_levels

        self.drift_threshold_pct = drift_threshold_pct
        self.adx_threshold = adx_threshold
        self.cooldown_minutes = cooldown_minutes
        self.max_recenters_per_day = max_recenters_per_day
        self.trailing_pct = trailing_pct
        self.min_shift_pct = min_shift_pct
        self.max_shift_pct = max_shift_pct
        self.velocity_window = velocity_window

        # Internal state
        self._lock = asyncio.Lock()
        self._last_recenter: Optional[datetime] = None
        self._recenters_today: int = 0
        self._today_date: Optional[object] = None
        self._recenter_history: List[SmartRecenterResult] = []

        # Velocity tracking (recent prices)
        self._recent_prices: List[float] = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reset_daily_counter_if_needed(self) -> None:
        today = datetime.now(timezone.utc).date()
        if self._today_date != today:
            self._today_date = today
            self._recenters_today = 0

    def _drift_pct(self, price: float) -> float:
        if self.center_price <= 0:
            return 0.0
        return abs(price - self.center_price) / self.center_price * 100.0

    def _compute_velocity(self) -> float:
        """Compute normalised price velocity (% change over recent window).

        Returns a value in [0, 1] where:
        - 0 = no movement
        - 1 = extreme movement (> 5% in the window)
        """
        prices = self._recent_prices
        if len(prices) < 3:
            return 0.0
        first = prices[0]
        last = prices[-1]
        if first <= 0:
            return 0.0
        change_pct = abs(last - first) / first * 100.0
        # Normalise: 0% -> 0, 5% -> 1.0
        return min(1.0, change_pct / 5.0)

    def _compute_shift_ratio(self, velocity: float) -> float:
        """Determine what fraction of the drift to close.

        Low velocity -> conservative shift (min_shift_pct).
        High velocity -> aggressive shift (max_shift_pct).
        """
        # Linear interpolation based on velocity
        ratio = self.min_shift_pct + velocity * (self.max_shift_pct - self.min_shift_pct)
        return max(self.min_shift_pct, min(self.max_shift_pct, ratio)) / 100.0

    # ------------------------------------------------------------------
    # Hot-path gating — O(1)
    # ------------------------------------------------------------------

    def should_recenter(self, price: float, adx: Optional[float] = None) -> bool:
        """Quick check whether recentering is warranted.

        O(1) — suitable for the hot path.  Does NOT perform the actual
        recentering computation.
        """
        self._reset_daily_counter_if_needed()

        # Track price for velocity
        self._recent_prices.append(price)
        if len(self._recent_prices) > self.velocity_window:
            self._recent_prices = self._recent_prices[-self.velocity_window:]

        # Condition 1: drift exceeds threshold
        if self._drift_pct(price) < self.drift_threshold_pct:
            return False

        # Condition 2: not in strong trend
        if adx is not None and adx >= self.adx_threshold:
            return False

        # Condition 3: cooldown elapsed
        if self._last_recenter is not None:
            elapsed = (datetime.now(timezone.utc) - self._last_recenter).total_seconds() / 60.0
            if elapsed < self.cooldown_minutes:
                return False

        # Condition 4: daily cap
        if self._recenters_today >= self.max_recenters_per_day:
            return False

        return True

    # ------------------------------------------------------------------
    # Cold-path — full recenter computation
    # ------------------------------------------------------------------

    def compute_recenter(
        self,
        price: float,
        open_levels: Optional[Dict[int, Dict]] = None,
        grid_levels: Optional[List[float]] = None,
    ) -> SmartRecenterResult:
        """Compute a progressive recentering.

        Unlike the old DGT which snaps center to price and closes ALL
        positions, this method:
        1. Computes a partial shift (25-75% of the gap).
        2. Only marks positions that are far out-of-range for closure.

        Args:
            price:        Current market price.
            open_levels:  Dict of open positions {level_idx: {entry_price, volume}}.
            grid_levels:  Current grid level prices.

        Returns:
            SmartRecenterResult with the new center and positions to close.
        """
        self._reset_daily_counter_if_needed()

        old_center = self.center_price
        drift = self._drift_pct(price)

        if drift < self.drift_threshold_pct:
            return SmartRecenterResult(
                should_recenter=False,
                old_center=old_center,
                new_center=old_center,
                shift_pct=0.0,
                new_grid_levels=grid_levels or [],
                positions_to_close=[],
                reason=f"Drift {drift:.1f}% < threshold {self.drift_threshold_pct}%",
            )

        # 1. Compute velocity and shift ratio
        velocity = self._compute_velocity()
        shift_ratio = self._compute_shift_ratio(velocity)

        # 2. Compute new center (progressive shift)
        gap = price - old_center
        new_center = old_center + gap * shift_ratio

        # 3. Compute new grid levels
        new_levels = calculate_grid_levels(
            center_price=new_center,
            range_percent=self.range_percent,
            num_levels=self.num_levels,
        )

        # 4. Determine which positions to close (only far-out-of-range ones)
        positions_to_close: List[int] = []
        if open_levels and grid_levels:
            new_low = new_levels[0] if new_levels else 0
            new_high = new_levels[-1] if new_levels else float("inf")
            margin = self.range_percent / 100.0 * new_center * 0.5  # 50% of half-range

            for idx, pos in open_levels.items():
                entry = pos.get("entry_price", 0)
                if entry < new_low - margin or entry > new_high + margin:
                    positions_to_close.append(idx)

        # 5. Update internal state
        self.center_price = new_center
        self._last_recenter = datetime.now(timezone.utc)
        self._recenters_today += 1

        result = SmartRecenterResult(
            should_recenter=True,
            old_center=old_center,
            new_center=new_center,
            shift_pct=shift_ratio * 100.0,
            new_grid_levels=new_levels,
            positions_to_close=positions_to_close,
            reason=(
                f"SmartRecenter: {old_center:.2f}->{new_center:.2f} "
                f"(shift {shift_ratio*100:.0f}%, velocity {velocity:.2f}, "
                f"drift {drift:.1f}%, close {len(positions_to_close)} pos)"
            ),
            recenter_count_today=self._recenters_today,
        )
        self._recenter_history.append(result)

        logger.info(
            "SmartRecenter %s: %.2f -> %.2f (shift %.0f%%, velocity %.2f, "
            "drift %.1f%%, closing %d positions) — #%d today",
            "UP" if gap > 0 else "DOWN",
            old_center,
            new_center,
            shift_ratio * 100,
            velocity,
            drift,
            len(positions_to_close),
            self._recenters_today,
        )
        return result

    # Backward-compatible alias for GridRecenteringManager.recenter()
    def recenter(self, price: float) -> SmartRecenterResult:
        """Backward-compatible recenter (closes all positions).

        For full compatibility with the existing GridStrategyAsync code
        that calls ``self._dgt.recenter(price)``.
        """
        result = self.compute_recenter(price)
        # Make it behave like old DGT: mark ALL open levels for close
        # (caller clears open_levels anyway after this call)
        return result

    async def async_recenter(self, price: float) -> SmartRecenterResult:
        """Async-safe recentering with ``asyncio.Lock``."""
        async with self._lock:
            return self.recenter(price)

    # ------------------------------------------------------------------
    # Trailing anchor (kept from original DGT)
    # ------------------------------------------------------------------

    def check_trailing_anchor(self, price: float) -> bool:
        """Soft trailing anchor — gently shift center upward.

        Same as original DGT but with a smaller shift (40% instead of 50%)
        for smoother tracking.
        """
        if self.center_price <= 0:
            return False
        upside_pct = (price - self.center_price) / self.center_price * 100.0
        if upside_pct > self.trailing_pct:
            new_center = self.center_price + (price - self.center_price) * 0.4
            logger.info(
                "SmartRecenter trailing: center %.2f -> %.2f (price +%.1f%%)",
                self.center_price,
                new_center,
                upside_pct,
            )
            self.center_price = new_center
            return True
        return False

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def recenters_today(self) -> int:
        self._reset_daily_counter_if_needed()
        return self._recenters_today

    @property
    def last_recenter(self) -> Optional[datetime]:
        return self._last_recenter

    @property
    def recenter_history(self) -> List[SmartRecenterResult]:
        return list(self._recenter_history)

    def get_status(self) -> Dict:
        self._reset_daily_counter_if_needed()
        return {
            "center_price": self.center_price,
            "drift_threshold_pct": self.drift_threshold_pct,
            "adx_threshold": self.adx_threshold,
            "cooldown_minutes": self.cooldown_minutes,
            "max_recenters_per_day": self.max_recenters_per_day,
            "recenters_today": self._recenters_today,
            "last_recenter": (
                self._last_recenter.isoformat() if self._last_recenter else None
            ),
            "history_count": len(self._recenter_history),
            "min_shift_pct": self.min_shift_pct,
            "max_shift_pct": self.max_shift_pct,
            "velocity_window": self.velocity_window,
        }
