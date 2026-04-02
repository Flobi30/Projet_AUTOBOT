"""
Dynamic Grid Recentering (DGT) — AutoBot V2
Based on NTU 2025 academic paper on adaptive grid trading.

Expected improvement: +0.2 to +0.4 on Profit Factor by avoiding forced
liquidation when price drifts outside grid bounds.

When price drifts beyond the configured threshold, instead of terminating
with a loss, this manager recenters the grid around the current price.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .strategies import calculate_grid_levels

logger = logging.getLogger(__name__)


@dataclass
class RecenterResult:
    """Result of a grid recentering operation."""

    success: bool
    old_center: float
    new_center: float
    new_grid_levels: List[float]
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)
    recenter_count_today: int = 0


class GridRecenteringManager:
    """
    Dynamic Grid Recentering (DGT) manager.

    Detects when price drifts beyond ``drift_threshold_pct`` from the grid
    center and recenters the grid around the current price, preserving the
    remaining capital.

    Recentering is allowed only when ALL conditions are met:

    1. **Drift** — price deviation from center ≥ ``drift_threshold_pct`` (default 7 %)
    2. **No strong trend** — ADX < ``adx_threshold`` (default 25), if provided
    3. **Cooldown** — at least ``cooldown_minutes`` elapsed since last recenter (default 60)
    4. **Daily cap** — at most ``max_recenters_per_day`` recenters per calendar day (default 3)

    Trailing anchor (soft sliding grid):
        When price rises > ``trailing_pct`` (default 5 %) above the current center,
        the center is gently shifted to the midpoint between old center and price.
        This is a lightweight adjustment that does **not** consume the daily quota or
        reset the cooldown. It makes a full recenter less likely by following gentle
        upward trends.

    Thread safety:
        ``async_recenter`` uses ``asyncio.Lock``. Synchronous ``recenter`` and
        ``should_recenter`` are safe when called from a single-threaded event loop
        (which is the normal asyncio use-case).
    """

    def __init__(
        self,
        center_price: float,
        range_percent: float,
        num_levels: int,
        drift_threshold_pct: float = 7.0,
        adx_threshold: float = 25.0,
        cooldown_minutes: int = 60,
        max_recenters_per_day: int = 3,
        trailing_pct: float = 5.0,
    ) -> None:
        self.center_price = center_price
        self.range_percent = range_percent
        self.num_levels = num_levels
        self.drift_threshold_pct = drift_threshold_pct
        self.adx_threshold = adx_threshold
        self.cooldown_minutes = cooldown_minutes
        self.max_recenters_per_day = max_recenters_per_day
        self.trailing_pct = trailing_pct

        self._lock = asyncio.Lock()
        self._last_recenter: Optional[datetime] = None
        self._recenters_today: int = 0
        self._today_date: Optional[object] = None  # datetime.date
        self._recenter_history: List[RecenterResult] = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reset_daily_counter_if_needed(self) -> None:
        """Reset the daily counter when the calendar date changes."""
        today = datetime.now().date()
        if self._today_date != today:
            self._today_date = today
            self._recenters_today = 0

    def _drift_pct(self, price: float) -> float:
        """Return the absolute drift percentage from the current center."""
        if self.center_price <= 0:
            return 0.0
        return abs(price - self.center_price) / self.center_price * 100.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_recenter(self, price: float, adx: Optional[float] = None) -> bool:
        """
        Check whether a recentering is warranted right now.

        Args:
            price: Current market price.
            adx:   Current ADX value (optional). When provided and ≥ ``adx_threshold``,
                   recentering is blocked to avoid chasing a strong trend.

        Returns:
            ``True`` if all four conditions (drift, trend, cooldown, daily cap) are met.
        """
        self._reset_daily_counter_if_needed()

        # Condition 1 — drift exceeds threshold
        if self._drift_pct(price) < self.drift_threshold_pct:
            return False

        # Condition 2 — not in strong trend
        if adx is not None and adx >= self.adx_threshold:
            logger.debug(
                "DGT: blocked — strong trend ADX=%.1f >= %.1f", adx, self.adx_threshold
            )
            return False

        # Condition 3 — cooldown elapsed
        if self._last_recenter is not None:
            elapsed_min = (datetime.now() - self._last_recenter).total_seconds() / 60.0
            if elapsed_min < self.cooldown_minutes:
                logger.debug(
                    "DGT: blocked — cooldown %.1f / %d min remaining",
                    elapsed_min,
                    self.cooldown_minutes,
                )
                return False

        # Condition 4 — daily cap not reached
        if self._recenters_today >= self.max_recenters_per_day:
            logger.debug(
                "DGT: blocked — daily cap %d reached", self.max_recenters_per_day
            )
            return False

        return True

    def recenter(self, price: float) -> RecenterResult:
        """
        Perform a synchronous recentering around *price*.

        Updates internal state (``center_price``, counters) and returns a
        ``RecenterResult`` with the new grid levels. The caller is responsible
        for applying ``result.new_grid_levels`` to the active strategy and
        closing any open positions beforehand.

        Args:
            price: New center price (normally the current market price).

        Returns:
            ``RecenterResult`` with ``success=True`` and the new grid levels.
        """
        self._reset_daily_counter_if_needed()

        old_center = self.center_price
        drift_pct = abs(price - old_center) / old_center * 100.0 if old_center > 0 else 0.0

        self.center_price = price
        new_levels = calculate_grid_levels(
            center_price=price,
            range_percent=self.range_percent,
            num_levels=self.num_levels,
        )

        self._last_recenter = datetime.now()
        self._recenters_today += 1

        result = RecenterResult(
            success=True,
            old_center=old_center,
            new_center=price,
            new_grid_levels=new_levels,
            reason=f"DGT: {old_center:.2f}→{price:.2f} (drift {drift_pct:.1f}%)",
            timestamp=datetime.now(),
            recenter_count_today=self._recenters_today,
        )
        self._recenter_history.append(result)

        logger.info(
            "✅ DGT: Grid recentered %.2f → %.2f — drift %.1f%% — recenter #%d today",
            old_center,
            price,
            drift_pct,
            self._recenters_today,
        )
        return result

    async def async_recenter(self, price: float) -> RecenterResult:
        """
        Async-safe recentering with ``asyncio.Lock``.

        Use this variant when multiple coroutines could call ``recenter``
        concurrently (e.g., a websocket callback racing with a scheduled task).
        For the normal hot-path (single event-loop tick), ``recenter`` is fine.
        """
        async with self._lock:
            return self.recenter(price)

    def check_trailing_anchor(self, price: float) -> bool:
        """
        Soft trailing anchor — gently shift center upward when price rises
        more than ``trailing_pct`` above the current center.

        The center is moved to the midpoint between old center and price
        (a 50 % shift). This does **not** count toward the daily quota and
        does **not** reset the cooldown timer.

        Returns:
            ``True`` if the center was shifted; ``False`` otherwise.
        """
        if self.center_price <= 0:
            return False
        upside_pct = (price - self.center_price) / self.center_price * 100.0
        if upside_pct > self.trailing_pct:
            new_center = self.center_price + (price - self.center_price) * 0.5
            logger.info(
                "⚓ DGT trailing anchor: center %.2f → %.2f (price +%.1f%%)",
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
        """Number of recenterings performed today (resets at midnight)."""
        self._reset_daily_counter_if_needed()
        return self._recenters_today

    @property
    def last_recenter(self) -> Optional[datetime]:
        """Timestamp of the last recentering, or ``None`` if never recentered."""
        return self._last_recenter

    @property
    def recenter_history(self) -> List[RecenterResult]:
        """Read-only view of the full recentering history."""
        return list(self._recenter_history)

    def get_status(self) -> Dict:
        """Return a JSON-serialisable snapshot of the manager state."""
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
        }
