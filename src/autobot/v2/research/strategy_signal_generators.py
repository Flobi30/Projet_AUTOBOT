"""Research-only signal generators for AUTOBOT strategy families.

These classes are adapters for validation, not production strategies. They make
the existing grid/trend/mean-reversion hypotheses measurable through the common
`BacktestEngine` contract while keeping runtime paper/live execution unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Iterable, Mapping, Sequence

from .backtest_engine import BacktestSignal
from .market_data_repository import MarketBar


def _bps_to_rate(value: float) -> float:
    return float(value) / 10_000.0


def _returns_bps(prices: Sequence[float]) -> list[float]:
    values: list[float] = []
    for index in range(1, len(prices)):
        previous = prices[index - 1]
        current = prices[index]
        if previous > 0.0 and current > 0.0:
            values.append(((current / previous) - 1.0) * 10_000.0)
    return values


def _atr_bps(prices: Sequence[float], window: int) -> float:
    returns = [abs(value) for value in _returns_bps(prices)]
    if not returns:
        return 0.0
    tail = returns[-max(1, int(window)) :]
    return sum(tail) / len(tail)


@dataclass(frozen=True)
class GridResearchConfig:
    strategy_id: str = "dynamic_grid"
    range_percent: float = 3.0
    num_levels: int = 9
    entry_touch_bps: float = 8.0
    take_profit_bps: float = 45.0
    stop_loss_bps: float = 180.0
    recenter_bps: float = 250.0
    order_notional_eur: float | None = None


class GridResearchSignalGenerator:
    """Grid-family producer for bar replay validation."""

    def __init__(self, config: GridResearchConfig | None = None) -> None:
        self.config = config or GridResearchConfig()
        self._center_price: float | None = None
        self._in_position = False
        self._entry_price: float | None = None
        self._entry_level: float | None = None

    def __call__(self, bar: MarketBar, history: Sequence[MarketBar]) -> Iterable[BacktestSignal]:
        price = float(bar.close)
        if self._center_price is None:
            self._center_price = price
        if abs((price / max(self._center_price, 1e-12)) - 1.0) * 10_000.0 > self.config.recenter_bps:
            if not self._in_position:
                self._center_price = price

        if self._in_position and self._entry_price:
            profit_bps = ((price / self._entry_price) - 1.0) * 10_000.0
            if profit_bps >= self.config.take_profit_bps:
                self._in_position = False
                return [self._signal(bar, "sell", "grid_take_profit", gross_edge_bps=profit_bps)]
            if profit_bps <= -abs(self.config.stop_loss_bps):
                self._in_position = False
                return [self._signal(bar, "sell", "grid_stop_loss", gross_edge_bps=profit_bps)]
            return []

        level = self._nearest_buy_level(price)
        if level is None:
            return []
        touch_bps = ((level / max(price, 1e-12)) - 1.0) * 10_000.0
        if abs(touch_bps) <= self.config.entry_touch_bps or price <= level:
            self._in_position = True
            self._entry_price = price
            self._entry_level = level
            return [self._signal(bar, "buy", "grid_support_touch", gross_edge_bps=self.config.take_profit_bps)]
        return []

    def _levels(self) -> list[float]:
        if self._center_price is None:
            return []
        count = max(2, int(self.config.num_levels))
        half_range = self.config.range_percent / 2.0
        step = self.config.range_percent / (count - 1)
        return sorted(self._center_price * (1.0 + ((-half_range + index * step) / 100.0)) for index in range(count))

    def _nearest_buy_level(self, price: float) -> float | None:
        center = float(self._center_price or 0.0)
        levels = [
            level
            for level in self._levels()
            if level < center and level <= price * (1.0 + _bps_to_rate(self.config.entry_touch_bps))
        ]
        if not levels:
            return None
        return min(levels, key=lambda level: abs(price - level))

    def _signal(self, bar: MarketBar, side: str, reason: str, *, gross_edge_bps: float) -> BacktestSignal:
        return BacktestSignal(
            symbol=bar.symbol,
            side=side,
            price=bar.close,
            timestamp=bar.timestamp,
            reason=reason,
            notional_eur=self.config.order_notional_eur if side == "buy" else None,
            metadata={
                "strategy_id": self.config.strategy_id,
                "strategy_family": "grid",
                "gross_edge_bps": gross_edge_bps,
                "grid_center": self._center_price,
                "grid_entry_level": self._entry_level,
                "regime": bar.metadata.get("regime", "unknown"),
            },
        )


@dataclass(frozen=True)
class TrendResearchConfig:
    strategy_id: str = "trend_momentum"
    breakout_window: int = 24
    exit_window: int = 12
    momentum_window: int = 8
    atr_window: int = 14
    confirm_bps: float = 20.0
    min_momentum_bps: float = 25.0
    min_atr_bps: float = 8.0
    trailing_atr_mult: float = 2.5
    stop_atr_mult: float = 2.0
    order_notional_eur: float | None = None


class TrendResearchSignalGenerator:
    """Donchian/momentum trend producer for replay validation."""

    def __init__(self, config: TrendResearchConfig | None = None) -> None:
        self.config = config or TrendResearchConfig()
        self._in_position = False
        self._entry_price: float | None = None
        self._highest_price: float | None = None

    def __call__(self, bar: MarketBar, history: Sequence[MarketBar]) -> Iterable[BacktestSignal]:
        prices = [float(item.close) for item in history]
        previous = prices[:-1]
        price = float(bar.close)
        if self._in_position:
            self._highest_price = max(float(self._highest_price or price), price)
            features = self._features(prices)
            atr_price = price * _bps_to_rate(max(features.get("atr_bps", 0.0), 1.0))
            stop_price = float(self._entry_price or price) - (self.config.stop_atr_mult * atr_price)
            trailing_stop = float(self._highest_price or price) - (self.config.trailing_atr_mult * atr_price)
            exit_low = features.get("exit_low")
            if price <= max(stop_price, trailing_stop) or (exit_low is not None and price < float(exit_low)):
                self._in_position = False
                gross_edge = ((price / max(float(self._entry_price or price), 1e-12)) - 1.0) * 10_000.0
                return [self._signal(bar, "sell", "trend_exit", gross_edge_bps=gross_edge, features=features)]
            return []

        if len(previous) < max(self.config.breakout_window, self.config.momentum_window, self.config.atr_window):
            return []
        previous_high = max(previous[-self.config.breakout_window :])
        momentum_base = previous[-self.config.momentum_window]
        momentum_bps = ((price / max(momentum_base, 1e-12)) - 1.0) * 10_000.0
        breakout_bps = ((price / max(previous_high, 1e-12)) - 1.0) * 10_000.0
        atr_bps = _atr_bps(previous + [price], self.config.atr_window)
        if (
            breakout_bps >= self.config.confirm_bps
            and momentum_bps >= self.config.min_momentum_bps
            and atr_bps >= self.config.min_atr_bps
        ):
            self._in_position = True
            self._entry_price = price
            self._highest_price = price
            features = {"breakout_bps": breakout_bps, "momentum_bps": momentum_bps, "atr_bps": atr_bps}
            return [self._signal(bar, "buy", "trend_breakout", gross_edge_bps=momentum_bps, features=features)]
        return []

    def _features(self, prices: Sequence[float]) -> dict[str, float | None]:
        return {
            "atr_bps": _atr_bps(prices, self.config.atr_window),
            "exit_low": min(prices[-self.config.exit_window - 1 : -1]) if len(prices) > self.config.exit_window else None,
        }

    def _signal(
        self,
        bar: MarketBar,
        side: str,
        reason: str,
        *,
        gross_edge_bps: float,
        features: Mapping[str, float | None],
    ) -> BacktestSignal:
        return BacktestSignal(
            symbol=bar.symbol,
            side=side,
            price=bar.close,
            timestamp=bar.timestamp,
            reason=reason,
            notional_eur=self.config.order_notional_eur if side == "buy" else None,
            metadata={
                "strategy_id": self.config.strategy_id,
                "strategy_family": "trend",
                "gross_edge_bps": gross_edge_bps,
                **dict(features),
                "regime": bar.metadata.get("regime", "unknown"),
            },
        )


@dataclass(frozen=True)
class MeanReversionResearchConfig:
    strategy_id: str = "mean_reversion"
    window: int = 20
    entry_z: float = 2.0
    exit_z: float = 0.25
    stop_z: float = 3.0
    atr_window: int = 14
    min_atr_bps: float = 3.0
    max_abs_trend_bps: float = 180.0
    min_expected_edge_bps: float = 25.0
    order_notional_eur: float | None = None


class MeanReversionResearchSignalGenerator:
    """Bollinger/z-score mean-reversion producer for replay validation."""

    def __init__(self, config: MeanReversionResearchConfig | None = None) -> None:
        self.config = config or MeanReversionResearchConfig()
        self._in_position = False
        self._entry_price: float | None = None
        self._std_at_entry: float | None = None

    def __call__(self, bar: MarketBar, history: Sequence[MarketBar]) -> Iterable[BacktestSignal]:
        prices = [float(item.close) for item in history]
        previous = prices[:-1]
        price = float(bar.close)
        if len(previous) < max(self.config.window, self.config.atr_window):
            return []
        window = previous[-self.config.window :]
        avg = mean(window)
        std = pstdev(window)
        if std <= 0.0 or not math.isfinite(std):
            return []
        z_score = (price - avg) / std
        atr_bps = _atr_bps(previous + [price], self.config.atr_window)
        trend_base = previous[-self.config.window]
        trend_bps = ((price / max(trend_base, 1e-12)) - 1.0) * 10_000.0
        features = {
            "z_score": z_score,
            "mean": avg,
            "std": std,
            "atr_bps": atr_bps,
            "trend_bps": trend_bps,
        }
        if self._in_position:
            stop_price = float(self._entry_price or price) - (abs(self.config.stop_z) * max(float(self._std_at_entry or std), 1e-12))
            if z_score >= -abs(self.config.exit_z):
                self._in_position = False
                gross_edge = ((price / max(float(self._entry_price or price), 1e-12)) - 1.0) * 10_000.0
                return [self._signal(bar, "sell", "mean_reversion_exit", gross_edge_bps=gross_edge, features=features)]
            if price <= stop_price:
                self._in_position = False
                gross_edge = ((price / max(float(self._entry_price or price), 1e-12)) - 1.0) * 10_000.0
                return [self._signal(bar, "sell", "mean_reversion_stop", gross_edge_bps=gross_edge, features=features)]
            return []

        expected_edge_bps = ((avg / max(price, 1e-12)) - 1.0) * 10_000.0
        if (
            z_score <= -abs(self.config.entry_z)
            and atr_bps >= self.config.min_atr_bps
            and abs(trend_bps) <= self.config.max_abs_trend_bps
            and expected_edge_bps >= self.config.min_expected_edge_bps
        ):
            self._in_position = True
            self._entry_price = price
            self._std_at_entry = std
            return [
                self._signal(
                    bar,
                    "buy",
                    "mean_reversion_zscore_entry",
                    gross_edge_bps=expected_edge_bps,
                    features=features,
                )
            ]
        return []

    def _signal(
        self,
        bar: MarketBar,
        side: str,
        reason: str,
        *,
        gross_edge_bps: float,
        features: Mapping[str, float],
    ) -> BacktestSignal:
        return BacktestSignal(
            symbol=bar.symbol,
            side=side,
            price=bar.close,
            timestamp=bar.timestamp,
            reason=reason,
            notional_eur=self.config.order_notional_eur if side == "buy" else None,
            metadata={
                "strategy_id": self.config.strategy_id,
                "strategy_family": "mean_reversion",
                "gross_edge_bps": gross_edge_bps,
                **dict(features),
                "regime": bar.metadata.get("regime", "unknown"),
            },
        )
