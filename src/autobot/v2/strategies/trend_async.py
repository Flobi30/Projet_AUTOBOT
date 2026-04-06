"""
Trend Following Strategy — Async version
MIGRATION P0: Replaces trend.py (threading.RLock → no lock in async)

Identical logic, O(1) indicators. No threading primitives.
"""

from __future__ import annotations

import logging
import math
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import TradingSignal, SignalType, RollingEMA, RollingRSI, PositionSizing
from .strategy_async import StrategyAsync

logger = logging.getLogger(__name__)


class TrendStrategyAsync(StrategyAsync):
    """Async Trend Following Strategy with O(1) indicators."""

    def __init__(self, instance: Any, config: Optional[Dict] = None) -> None:
        super().__init__(instance, config)

        self.fast_period = self.config.get("fast_ma", 10)
        self.slow_period = self.config.get("slow_ma", 30)
        self.rsi_period = self.config.get("rsi_period", 14)
        self.rsi_overbought = self.config.get("rsi_overbought", 70)
        self.rsi_oversold = self.config.get("rsi_oversold", 30)
        self.min_trend_strength = self.config.get("min_trend_strength", 1.0)

        self._price_history: deque = deque(maxlen=200)
        self._fast_ma = RollingEMA(self.fast_period)
        self._slow_ma = RollingEMA(self.slow_period)
        self._rsi = RollingRSI(self.rsi_period)

        self._initialized = True
        self._current_trend = "neutral"
        self._entry_price: Optional[float] = None

        logger.info(
            f"📈 TrendAsync: MA{self.fast_period}/MA{self.slow_period}, "
            f"RSI({self.rsi_period}) [O(1)]"
        )

    def _calculate_indicators(self) -> Dict[str, Any]:
        fast = self._fast_ma.get_current()
        slow = self._slow_ma.get_current()
        rsi = self._rsi.get_current()
        if fast is None or slow is None or rsi is None:
            return {"ready": False}
        diff_pct = (fast - slow) / slow * 100 if slow else 0
        if diff_pct > self.min_trend_strength:
            trend = "up"
        elif diff_pct < -self.min_trend_strength:
            trend = "down"
        else:
            trend = "neutral"
        return {"ready": True, "fast_ma": fast, "slow_ma": slow, "rsi": rsi, "trend": trend, "diff_pct": diff_pct}

    def _should_buy(self, ind: Dict) -> bool:
        if not ind["ready"] or ind["trend"] != "up":
            return False
        if ind["diff_pct"] < self.min_trend_strength:
            return False
        if ind["rsi"] and ind["rsi"] > self.rsi_overbought:
            return False
        return True

    def _should_sell(self, ind: Dict, price: float) -> bool:
        if not ind["ready"]:
            return False
        if ind["trend"] == "down":
            return True
        if ind["rsi"] and ind["rsi"] > 80:
            return True
        if self._entry_price and price < self._entry_price * 0.95:
            return True
        return False

    def _has_open_position(self) -> bool:
        try:
            return len(self.instance.get_positions_snapshot()) > 0
        except Exception:
            return False

    def on_price(self, price: float) -> None:
        if not self._initialized or not math.isfinite(price) or price <= 0:
            return
        self._price_history.append(price)
        self._fast_ma.update(price)
        self._slow_ma.update(price)
        self._rsi.update(price)
        ind = self._calculate_indicators()
        self._current_trend = ind.get("trend", "neutral")

        symbol = self.instance.config.symbol
        has_pos = self._has_open_position()

        if has_pos:
            if self._should_sell(ind, price):
                sig = TradingSignal(
                    type=SignalType.SELL, symbol=symbol, price=price, volume=-1,
                    reason=f"Trend reversal: {ind['trend']} (MA diff: {ind['diff_pct']:.2f}%)",
                    timestamp=datetime.now(timezone.utc),
                    metadata={"strategy": "trend", "close_all": True, **{k: ind.get(k) for k in ("fast_ma", "slow_ma", "rsi", "trend")}},
                )
                self.emit_signal(sig)
        else:
            if self._should_buy(ind):
                avail = self.instance.get_current_capital()
                volume = PositionSizing.percentage_capital(avail, 20) / price
                sig = TradingSignal(
                    type=SignalType.BUY, symbol=symbol, price=price, volume=volume,
                    reason=f"Uptrend: MA{self.fast_period} > MA{self.slow_period} ({ind['diff_pct']:.2f}%)",
                    timestamp=datetime.now(timezone.utc),
                    metadata={"strategy": "trend", **{k: ind.get(k) for k in ("fast_ma", "slow_ma", "rsi", "trend")}},
                )
                self.emit_signal(sig)

    def on_position_opened(self, position: Any) -> None:
        if hasattr(position, "buy_price"):
            self._entry_price = position.buy_price

    def on_position_closed(self, position: Any, profit: float) -> None:
        self._entry_price = None

    def reset(self) -> None:
        self._entry_price = None
        self._current_trend = "neutral"
        self._price_history.clear()
        super().reset()
