"""Research-only signal generators for AUTOBOT strategy families.

These classes are adapters for validation, not production strategies. They make
the existing grid/trend/mean-reversion hypotheses measurable through the common
`BacktestEngine` contract while keeping runtime paper/live execution unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Iterable, Literal, Mapping, Sequence

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


def _bar_regime_metadata(bar: MarketBar) -> dict[str, object]:
    metadata: dict[str, object] = {"regime": bar.metadata.get("regime", "unknown")}
    if "regime_context" in bar.metadata:
        metadata["regime_context"] = bar.metadata["regime_context"]
    if "regime_source" in bar.metadata:
        metadata["regime_source"] = bar.metadata["regime_source"]
    return metadata


def _bar_regime(bar: MarketBar) -> str:
    regime = bar.metadata.get("regime")
    context = bar.metadata.get("regime_context")
    if (not regime or regime == "unknown") and isinstance(context, Mapping):
        regime = context.get("regime")
    return str(regime or "unknown")


def _bar_spread_bps(bar: MarketBar) -> float | None:
    direct = _metadata_float(bar.metadata, "spread_bps", "estimated_spread_bps")
    if direct is not None:
        return direct
    bid = _metadata_float(bar.metadata, "bid", "best_bid")
    ask = _metadata_float(bar.metadata, "ask", "best_ask")
    mid = (bid + ask) / 2.0 if bid is not None and ask is not None else None
    if bid is not None and ask is not None and mid and mid > 0.0:
        return ((ask - bid) / mid) * 10_000.0
    return None


def _metadata_float(metadata: Mapping[str, object], *keys: str) -> float | None:
    for key in keys:
        value = metadata.get(key)
        if value in (None, ""):
            continue
        try:
            result = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(result):
            return result
    return None


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
    estimated_round_trip_cost_bps: float = 50.0
    min_expected_mfe_to_cost: float | None = None
    atr_window: int = 14
    min_atr_bps: float | None = None
    max_atr_bps: float | None = None
    max_spread_bps: float | None = None
    support_confirmation_bars: int = 0
    blocked_regimes: tuple[str, ...] = ()
    allowed_regimes: tuple[str, ...] = ()
    exit_mode: Literal[
        "baseline",
        "cost_buffered_tp",
        "mfe_trailing",
        "time_stop_no_mfe",
        "decaying_net_edge",
    ] = "baseline"
    cost_buffer_bps: float = 20.0
    mfe_trailing_activation_bps: float = 70.0
    mfe_trailing_drawdown_bps: float = 35.0
    max_hold_bars: int | None = None
    min_mfe_before_time_stop_bps: float | None = None
    decay_min_profit_bps: float = 10.0
    decay_giveback_bps: float = 25.0

    def __post_init__(self) -> None:
        if not str(self.strategy_id).strip():
            raise ValueError("strategy_id must not be empty")
        if self.range_percent <= 0.0 or not math.isfinite(self.range_percent):
            raise ValueError("range_percent must be positive and finite")
        if self.num_levels < 2:
            raise ValueError("num_levels must be at least 2")
        for field_name in (
            "entry_touch_bps",
            "take_profit_bps",
            "stop_loss_bps",
            "recenter_bps",
            "estimated_round_trip_cost_bps",
            "cost_buffer_bps",
            "mfe_trailing_activation_bps",
            "mfe_trailing_drawdown_bps",
            "decay_min_profit_bps",
            "decay_giveback_bps",
        ):
            value = float(getattr(self, field_name))
            if value < 0.0 or not math.isfinite(value):
                raise ValueError(f"{field_name} must be non-negative and finite")
        if self.atr_window <= 0:
            raise ValueError("atr_window must be positive")
        for field_name in (
            "order_notional_eur",
            "min_expected_mfe_to_cost",
            "min_atr_bps",
            "max_atr_bps",
            "max_spread_bps",
            "min_mfe_before_time_stop_bps",
        ):
            value = getattr(self, field_name)
            if value is not None and (float(value) < 0.0 or not math.isfinite(float(value))):
                raise ValueError(f"{field_name} must be non-negative and finite when provided")
        if self.max_hold_bars is not None and self.max_hold_bars <= 0:
            raise ValueError("max_hold_bars must be positive when provided")
        if self.support_confirmation_bars < 0:
            raise ValueError("support_confirmation_bars must not be negative")
        valid_exit_modes = {
            "baseline",
            "cost_buffered_tp",
            "mfe_trailing",
            "time_stop_no_mfe",
            "decaying_net_edge",
        }
        if self.exit_mode not in valid_exit_modes:
            raise ValueError(f"unsupported grid exit_mode: {self.exit_mode}")
        object.__setattr__(self, "blocked_regimes", tuple(str(item) for item in self.blocked_regimes))
        object.__setattr__(self, "allowed_regimes", tuple(str(item) for item in self.allowed_regimes))


class GridResearchSignalGenerator:
    """Grid-family producer for bar replay validation."""

    def __init__(self, config: GridResearchConfig | None = None) -> None:
        self.config = config or GridResearchConfig()
        self._center_price: float | None = None
        self._in_position = False
        self._entry_price: float | None = None
        self._entry_level: float | None = None
        self._highest_price: float | None = None
        self._bars_in_position = 0

    def __call__(self, bar: MarketBar, history: Sequence[MarketBar]) -> Iterable[BacktestSignal]:
        price = float(bar.close)
        if self._center_price is None:
            self._center_price = price
        if abs((price / max(self._center_price, 1e-12)) - 1.0) * 10_000.0 > self.config.recenter_bps:
            if not self._in_position:
                self._center_price = price

        if self._in_position and self._entry_price:
            self._bars_in_position += 1
            self._highest_price = max(float(self._highest_price or price), float(bar.high), price)
            profit_bps = ((price / self._entry_price) - 1.0) * 10_000.0
            highest_profit_bps = ((float(self._highest_price or price) / self._entry_price) - 1.0) * 10_000.0
            giveback_bps = max(0.0, highest_profit_bps - profit_bps)
            exit_metadata = {
                "exit_mode": self.config.exit_mode,
                "bars_in_position": self._bars_in_position,
                "highest_profit_bps": highest_profit_bps,
                "giveback_bps": giveback_bps,
                "estimated_round_trip_cost_bps": self.config.estimated_round_trip_cost_bps,
            }
            if profit_bps <= -abs(self.config.stop_loss_bps):
                signal = self._signal(
                    bar,
                    "sell",
                    "grid_stop_loss",
                    gross_edge_bps=profit_bps,
                    features=exit_metadata,
                )
                self._reset_position()
                return [signal]
            exit_reason = self._research_exit_reason(
                gross_edge_bps=profit_bps,
                highest_profit_bps=highest_profit_bps,
                giveback_bps=giveback_bps,
            )
            if exit_reason is not None:
                signal = self._signal(
                    bar,
                    "sell",
                    exit_reason,
                    gross_edge_bps=profit_bps,
                    features=exit_metadata,
                )
                self._reset_position()
                return [signal]
            return []

        level = self._nearest_buy_level(price)
        if level is None:
            return []
        touch_bps = ((level / max(price, 1e-12)) - 1.0) * 10_000.0
        if abs(touch_bps) <= self.config.entry_touch_bps or price <= level:
            features = self._entry_features(bar, history, level=level, touch_bps=touch_bps)
            blocker = self._entry_filter_blocker(features)
            if blocker is not None:
                return []
            self._in_position = True
            self._entry_price = price
            self._entry_level = level
            self._highest_price = price
            self._bars_in_position = 0
            return [
                self._signal(
                    bar,
                    "buy",
                    "grid_support_touch",
                    gross_edge_bps=self.config.take_profit_bps,
                    features=features,
                )
            ]
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

    def _research_exit_reason(
        self,
        *,
        gross_edge_bps: float,
        highest_profit_bps: float,
        giveback_bps: float,
    ) -> str | None:
        if self.config.exit_mode == "mfe_trailing":
            if (
                highest_profit_bps >= self.config.mfe_trailing_activation_bps
                and giveback_bps >= self.config.mfe_trailing_drawdown_bps
            ):
                return "grid_mfe_trailing_exit"
        if self.config.exit_mode == "time_stop_no_mfe":
            min_mfe = self.config.min_mfe_before_time_stop_bps
            if min_mfe is None:
                min_mfe = self.config.estimated_round_trip_cost_bps
            if (
                self.config.max_hold_bars is not None
                and self._bars_in_position >= self.config.max_hold_bars
                and highest_profit_bps < min_mfe
            ):
                return "grid_time_stop_no_mfe"
        if self.config.exit_mode == "decaying_net_edge":
            if (
                gross_edge_bps > self.config.decay_min_profit_bps
                and highest_profit_bps >= self.config.estimated_round_trip_cost_bps
                and giveback_bps >= self.config.decay_giveback_bps
            ):
                return "grid_decaying_net_edge_exit"
        take_profit_bps = self.config.take_profit_bps
        if self.config.exit_mode == "cost_buffered_tp":
            take_profit_bps = max(
                take_profit_bps,
                self.config.estimated_round_trip_cost_bps + self.config.cost_buffer_bps,
            )
        if gross_edge_bps >= take_profit_bps:
            return "grid_cost_buffered_take_profit" if self.config.exit_mode == "cost_buffered_tp" else "grid_take_profit"
        return None

    def _entry_features(
        self,
        bar: MarketBar,
        history: Sequence[MarketBar],
        *,
        level: float,
        touch_bps: float,
    ) -> dict[str, object]:
        prices = [float(item.close) for item in history]
        atr_bps = _atr_bps(prices, self.config.atr_window)
        spread_bps = _bar_spread_bps(bar)
        expected_mfe_bps = self._expected_mfe_bps()
        cost_bps = max(float(self.config.estimated_round_trip_cost_bps), 1e-12)
        return {
            "exit_mode": self.config.exit_mode,
            "regime": _bar_regime(bar),
            "entry_touch_bps": touch_bps,
            "grid_entry_level": level,
            "atr_bps": atr_bps,
            "spread_bps": spread_bps,
            "estimated_mfe_bps": expected_mfe_bps,
            "estimated_round_trip_cost_bps": self.config.estimated_round_trip_cost_bps,
            "estimated_mfe_to_cost": expected_mfe_bps / cost_bps,
            "support_confirmation_bars": self.config.support_confirmation_bars,
            "support_confirmed": self._support_confirmed(level, history),
            "blocked_regimes": list(self.config.blocked_regimes),
            "allowed_regimes": list(self.config.allowed_regimes),
        }

    def _entry_filter_blocker(self, features: Mapping[str, object]) -> str | None:
        mfe_to_cost = float(features["estimated_mfe_to_cost"])
        if self.config.min_expected_mfe_to_cost is not None and mfe_to_cost < self.config.min_expected_mfe_to_cost:
            return "estimated_mfe_below_cost_threshold"
        regime = str(features.get("regime") or "unknown")
        if self.config.blocked_regimes and regime in self.config.blocked_regimes:
            return "blocked_regime"
        if self.config.allowed_regimes and regime not in self.config.allowed_regimes:
            return "regime_not_allowed"
        atr_bps = float(features["atr_bps"])
        if self.config.min_atr_bps is not None and atr_bps < self.config.min_atr_bps:
            return "volatility_too_low_for_costs"
        if self.config.max_atr_bps is not None and atr_bps > self.config.max_atr_bps:
            return "volatility_too_high_for_grid"
        spread = features.get("spread_bps")
        if self.config.max_spread_bps is not None and spread is not None and float(spread) > self.config.max_spread_bps:
            return "spread_too_high"
        if self.config.support_confirmation_bars and not bool(features["support_confirmed"]):
            return "support_confirmation_missing"
        return None

    def _expected_mfe_bps(self) -> float:
        expected = float(self.config.take_profit_bps)
        if self.config.exit_mode == "cost_buffered_tp":
            expected = max(expected, self.config.estimated_round_trip_cost_bps + self.config.cost_buffer_bps)
        return expected

    def _support_confirmed(self, level: float, history: Sequence[MarketBar]) -> bool:
        required = int(self.config.support_confirmation_bars)
        if required <= 0:
            return True
        previous = list(history[:-1])[-required:]
        if len(previous) < required:
            return False
        tolerance = 1.0 + _bps_to_rate(self.config.entry_touch_bps)
        return sum(1 for item in previous if float(item.low) <= level * tolerance) >= required

    def _reset_position(self) -> None:
        self._in_position = False
        self._entry_price = None
        self._entry_level = None
        self._highest_price = None
        self._bars_in_position = 0

    def _signal(
        self,
        bar: MarketBar,
        side: str,
        reason: str,
        *,
        gross_edge_bps: float,
        features: Mapping[str, object] | None = None,
    ) -> BacktestSignal:
        feature_payload = dict(features or {})
        feature_payload.setdefault("regime", _bar_regime(bar))
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
                **feature_payload,
                **_bar_regime_metadata(bar),
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
    exit_mode: Literal["baseline", "cost_buffer_tp", "mfe_trailing", "time_stop"] = "baseline"
    take_profit_bps: float | None = None
    mfe_trailing_activation_bps: float = 55.0
    mfe_trailing_drawdown_bps: float = 30.0
    max_hold_bars: int | None = None
    min_profit_before_time_exit_bps: float = 0.0


class TrendResearchSignalGenerator:
    """Donchian/momentum trend producer for replay validation."""

    def __init__(self, config: TrendResearchConfig | None = None) -> None:
        self.config = config or TrendResearchConfig()
        self._in_position = False
        self._entry_price: float | None = None
        self._highest_price: float | None = None
        self._bars_in_position = 0

    def __call__(self, bar: MarketBar, history: Sequence[MarketBar]) -> Iterable[BacktestSignal]:
        prices = [float(item.close) for item in history]
        previous = prices[:-1]
        price = float(bar.close)
        if self._in_position:
            self._bars_in_position += 1
            self._highest_price = max(float(self._highest_price or price), price)
            features = self._features(prices)
            entry_price = float(self._entry_price or price)
            gross_edge = ((price / max(entry_price, 1e-12)) - 1.0) * 10_000.0
            highest_profit_bps = ((float(self._highest_price or price) / max(entry_price, 1e-12)) - 1.0) * 10_000.0
            giveback_bps = max(0.0, highest_profit_bps - gross_edge)
            bars_in_position = self._bars_in_position
            exit_reason = self._research_exit_reason(
                gross_edge_bps=gross_edge,
                highest_profit_bps=highest_profit_bps,
                giveback_bps=giveback_bps,
            )
            if exit_reason is not None:
                self._reset_position()
                return [
                    self._signal(
                        bar,
                        "sell",
                        exit_reason,
                        gross_edge_bps=gross_edge,
                        features=features,
                        position_features={
                            "bars_in_position": bars_in_position,
                            "highest_profit_bps": highest_profit_bps,
                            "giveback_bps": giveback_bps,
                        },
                    )
                ]
            atr_price = price * _bps_to_rate(max(features.get("atr_bps", 0.0), 1.0))
            stop_price = entry_price - (self.config.stop_atr_mult * atr_price)
            trailing_stop = float(self._highest_price or price) - (self.config.trailing_atr_mult * atr_price)
            exit_low = features.get("exit_low")
            if price <= max(stop_price, trailing_stop) or (exit_low is not None and price < float(exit_low)):
                self._reset_position()
                return [
                    self._signal(
                        bar,
                        "sell",
                        "trend_exit",
                        gross_edge_bps=gross_edge,
                        features=features,
                        position_features={
                            "bars_in_position": bars_in_position,
                            "highest_profit_bps": highest_profit_bps,
                            "giveback_bps": giveback_bps,
                        },
                    )
                ]
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
            self._bars_in_position = 0
            features = {"breakout_bps": breakout_bps, "momentum_bps": momentum_bps, "atr_bps": atr_bps}
            return [self._signal(bar, "buy", "trend_breakout", gross_edge_bps=momentum_bps, features=features)]
        return []

    def _research_exit_reason(
        self,
        *,
        gross_edge_bps: float,
        highest_profit_bps: float,
        giveback_bps: float,
    ) -> str | None:
        if self.config.exit_mode == "cost_buffer_tp":
            take_profit_bps = self.config.take_profit_bps
            if take_profit_bps is not None and gross_edge_bps >= take_profit_bps:
                return "trend_cost_buffer_take_profit"
        if self.config.exit_mode == "mfe_trailing":
            if (
                highest_profit_bps >= self.config.mfe_trailing_activation_bps
                and giveback_bps >= self.config.mfe_trailing_drawdown_bps
            ):
                return "trend_mfe_trailing_exit"
        if self.config.exit_mode == "time_stop":
            if (
                self.config.max_hold_bars is not None
                and self._bars_in_position >= self.config.max_hold_bars
                and gross_edge_bps <= self.config.min_profit_before_time_exit_bps
            ):
                return "trend_time_stop"
        return None

    def _reset_position(self) -> None:
        self._in_position = False
        self._entry_price = None
        self._highest_price = None
        self._bars_in_position = 0

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
        position_features: Mapping[str, float | int] | None = None,
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
                "exit_mode": self.config.exit_mode,
                **dict(features),
                **dict(position_features or {}),
                **_bar_regime_metadata(bar),
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
                **_bar_regime_metadata(bar),
            },
        )
