"""
AdaptiveRangeCalculator — Dynamic grid range based on ATR + HV24/HV7d ratio.

Replaces the fixed ``range_percent = 7.0`` with a volatility-adaptive range.
Uses the existing ATRFilter for ATR data and computes a Historical Volatility
ratio (24h / 7d) to detect regime shifts (expanding vs contracting vol).

Hot-path: ``get_current_range()`` is O(1) — returns a cached float.
Cold-path: ``update()`` recomputes the range (~every 60s via ColdPathScheduler).

Thread-safe for asyncio (single-threaded event loop).
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from typing import Optional

from .adaptive_grid_config import PairProfile

__all__ = ["AdaptiveRangeCalculator"]

logger = logging.getLogger(__name__)


class AdaptiveRangeCalculator:
    """Compute the optimal grid range based on real-time volatility.

    The range is derived from two inputs:
    1. **ATR%** (from ATRFilter) — the baseline volatility measure.
    2. **HV ratio** (HV_24h / HV_7d) — detects whether volatility is
       expanding (ratio > 1) or contracting (ratio < 1).

    The formula:
        base_range = ATR% * profile.atr_multiplier
        regime_adj = clamp(hv_ratio, hv_band_low, hv_band_high)
        range_pct  = clamp(base_range * regime_adj, min_range, max_range)

    If no ATR data is available yet (warm-up), falls back to
    ``profile.base_range_pct``.
    """

    def __init__(
        self,
        profile: PairProfile,
        *,
        hv_24h_window: int = 1440,   # ~1 tick/min * 24h
        hv_7d_window: int = 10080,   # ~1 tick/min * 7d
        update_interval_s: float = 60.0,
    ) -> None:
        self._profile = profile
        self._hv_24h_window = hv_24h_window
        self._hv_7d_window = hv_7d_window
        self._update_interval_s = update_interval_s

        # Cached range — returned by get_current_range() in O(1)
        self._current_range_pct: float = profile.base_range_pct
        self._last_update_ts: float = 0.0

        # Price buffer for HV computation (rolling deque)
        self._prices_24h: deque = deque(maxlen=hv_24h_window)
        self._prices_7d: deque = deque(maxlen=hv_7d_window)

        # Last computed values (for introspection / dashboard)
        self._last_atr_pct: Optional[float] = None
        self._last_hv_ratio: Optional[float] = None
        self._last_hv_24h: Optional[float] = None
        self._last_hv_7d: Optional[float] = None

        logger.info(
            "AdaptiveRangeCalculator: %s — base=%.1f%%, range=[%.1f%%, %.1f%%], "
            "atr_mult=%.1f",
            profile.symbol,
            profile.base_range_pct,
            profile.min_range_pct,
            profile.max_range_pct,
            profile.atr_multiplier,
        )

    # ------------------------------------------------------------------
    # Hot-path — O(1)
    # ------------------------------------------------------------------

    def get_current_range(self) -> float:
        """Return the current adaptive range in %. O(1), no allocation."""
        return self._current_range_pct

    def on_price(self, price: float) -> None:
        """Ingest a price tick. O(1) deque append, no recomputation.

        Call this on every WS tick. The actual range recomputation
        happens in ``update()`` on the cold path.
        """
        if not math.isfinite(price) or price <= 0:
            return
        self._prices_24h.append(price)
        self._prices_7d.append(price)

    # ------------------------------------------------------------------
    # Cold-path — called periodically (~60s)
    # ------------------------------------------------------------------

    def update(self, atr_pct: Optional[float] = None) -> float:
        """Recompute the adaptive range. Called from ColdPathScheduler.

        Args:
            atr_pct: Current ATR% from ATRFilter. If None, uses
                     profile.base_range_pct as fallback.

        Returns:
            The updated range in %.
        """
        now = time.monotonic()

        # Throttle updates
        if now - self._last_update_ts < self._update_interval_s:
            return self._current_range_pct
        self._last_update_ts = now

        self._last_atr_pct = atr_pct

        # 1. Base range from ATR
        if atr_pct is not None and atr_pct > 0:
            base_range = atr_pct * self._profile.atr_multiplier
        else:
            base_range = self._profile.base_range_pct

        # 2. HV ratio regime adjustment
        hv_24h = self._compute_hv(self._prices_24h)
        hv_7d = self._compute_hv(self._prices_7d)
        self._last_hv_24h = hv_24h
        self._last_hv_7d = hv_7d

        regime_adj = 1.0
        if hv_24h is not None and hv_7d is not None and hv_7d > 0:
            hv_ratio = hv_24h / hv_7d
            self._last_hv_ratio = hv_ratio

            low, high = self._profile.hv_ratio_band
            # Clamp ratio to band then use as multiplier
            regime_adj = max(low, min(high, hv_ratio))
        else:
            self._last_hv_ratio = None

        # 3. Final range with clamping
        raw_range = base_range * regime_adj
        clamped = max(
            self._profile.min_range_pct,
            min(self._profile.max_range_pct, raw_range),
        )

        old = self._current_range_pct
        self._current_range_pct = clamped

        if abs(old - clamped) > 0.1:
            logger.info(
                "AdaptiveRange %s: %.2f%% -> %.2f%% "
                "(ATR=%.2f%%, HV_ratio=%.2f, regime_adj=%.2f)",
                self._profile.symbol,
                old,
                clamped,
                atr_pct or 0.0,
                self._last_hv_ratio or 0.0,
                regime_adj,
            )

        return clamped

    def force_update(self, atr_pct: Optional[float] = None) -> float:
        """Force an immediate range recomputation (ignores throttle)."""
        self._last_update_ts = 0.0
        return self.update(atr_pct)

    # ------------------------------------------------------------------
    # HV computation — O(N) but only on cold path
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_hv(prices: deque) -> Optional[float]:
        """Compute annualised historical volatility from a price series.

        Uses log-returns and standard deviation.  Returns None if fewer
        than 30 data points are available.
        """
        n = len(prices)
        if n < 30:
            return None

        # Compute mean of log-returns
        sum_lr = 0.0
        sum_lr_sq = 0.0
        prev = prices[0]
        count = 0
        for i in range(1, n):
            p = prices[i]
            if prev > 0 and p > 0:
                lr = math.log(p / prev)
                sum_lr += lr
                sum_lr_sq += lr * lr
                count += 1
            prev = p

        if count < 2:
            return None

        mean_lr = sum_lr / count
        variance = (sum_lr_sq / count) - (mean_lr * mean_lr)
        if variance < -1e-10:
            logger.warning("HV variance negative: %f, clamping to 0", variance)
            variance = 0.0
        # Return as percentage (not annualised — we compare ratios)
        return math.sqrt(variance) * 100.0

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        return {
            "symbol": self._profile.symbol,
            "current_range_pct": round(self._current_range_pct, 4),
            "base_range_pct": self._profile.base_range_pct,
            "min_range_pct": self._profile.min_range_pct,
            "max_range_pct": self._profile.max_range_pct,
            "atr_multiplier": self._profile.atr_multiplier,
            "last_atr_pct": round(self._last_atr_pct, 4) if self._last_atr_pct else None,
            "last_hv_ratio": round(self._last_hv_ratio, 4) if self._last_hv_ratio else None,
            "last_hv_24h": round(self._last_hv_24h, 6) if self._last_hv_24h else None,
            "last_hv_7d": round(self._last_hv_7d, 6) if self._last_hv_7d else None,
            "prices_24h_count": len(self._prices_24h),
            "prices_7d_count": len(self._prices_7d),
        }

    @property
    def profile(self) -> PairProfile:
        return self._profile
