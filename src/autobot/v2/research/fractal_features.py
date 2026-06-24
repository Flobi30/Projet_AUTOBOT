"""Observation-only fractal and volatility-clustering features for research."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import mean, pstdev
from typing import Any, Iterable, Sequence

from .market_data_repository import MarketBar


@dataclass(frozen=True)
class FractalVolatilityFeatures:
    symbol: str
    timeframe: str
    sample_count: int
    return_count: int
    hurst_exponent: float | None
    fractal_dimension: float | None
    volatility_bps: float | None
    volatility_short_to_long_ratio: float | None
    squared_return_autocorrelation: float | None
    regime_hint: str
    observation_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_fractal_volatility_features(
    bars: Iterable[MarketBar],
    *,
    preferred_timeframe: str = "15m",
) -> tuple[FractalVolatilityFeatures, ...]:
    """Describe price-memory and volatility conditions without trading impact."""

    grouped: dict[tuple[str, str], list[MarketBar]] = {}
    for bar in bars:
        grouped.setdefault((bar.symbol, bar.timeframe), []).append(bar)
    by_symbol: dict[str, tuple[str, list[MarketBar]]] = {}
    for (symbol, timeframe), rows in grouped.items():
        rows.sort(key=lambda item: item.timestamp)
        existing = by_symbol.get(symbol)
        if existing is None or (timeframe == preferred_timeframe and existing[0] != preferred_timeframe):
            by_symbol[symbol] = (timeframe, rows)
    return tuple(
        _features(symbol, timeframe, rows)
        for symbol, (timeframe, rows) in sorted(by_symbol.items())
    )


def _features(symbol: str, timeframe: str, rows: Sequence[MarketBar]) -> FractalVolatilityFeatures:
    prices = [float(item.close) for item in rows if item.close > 0.0]
    returns = [math.log(right / left) for left, right in zip(prices, prices[1:]) if left > 0.0 and right > 0.0]
    hurst = _hurst_exponent(returns)
    volatility = pstdev(returns) * 10_000.0 if len(returns) >= 2 else None
    ratio = _short_to_long_volatility_ratio(returns)
    clustering = _lag_one_correlation([value * value for value in returns])
    if not returns:
        regime = "insufficient_data"
    elif ratio is not None and ratio >= 1.5 and (clustering or 0.0) > 0.10:
        regime = "volatility_clustered"
    elif hurst is not None and hurst >= 0.60:
        regime = "persistent_trend_like"
    elif hurst is not None and hurst <= 0.40:
        regime = "mean_reverting_like"
    else:
        regime = "mixed_or_random_like"
    return FractalVolatilityFeatures(
        symbol=symbol,
        timeframe=timeframe,
        sample_count=len(prices),
        return_count=len(returns),
        hurst_exponent=hurst,
        fractal_dimension=(2.0 - hurst) if hurst is not None else None,
        volatility_bps=volatility,
        volatility_short_to_long_ratio=ratio,
        squared_return_autocorrelation=clustering,
        regime_hint=regime,
    )


def _hurst_exponent(returns: Sequence[float]) -> float | None:
    if len(returns) < 32:
        return None
    windows = [size for size in (8, 16, 32, 64, 128) if size <= len(returns)]
    xs: list[float] = []
    ys: list[float] = []
    for size in windows:
        values: list[float] = []
        for start in range(0, len(returns) - size + 1, size):
            segment = returns[start : start + size]
            deviation = pstdev(segment)
            if deviation <= 0.0:
                continue
            centered = [value - mean(segment) for value in segment]
            cumulative: list[float] = []
            running = 0.0
            for value in centered:
                running += value
                cumulative.append(running)
            rescaled_range = (max(cumulative) - min(cumulative)) / deviation
            if rescaled_range > 0.0:
                values.append(rescaled_range)
        if values:
            xs.append(math.log(size))
            ys.append(math.log(mean(values)))
    if len(xs) < 2:
        return None
    x_mean = mean(xs)
    y_mean = mean(ys)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    if denominator <= 0.0:
        return None
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
    return max(0.0, min(1.0, slope)) if math.isfinite(slope) else None


def _short_to_long_volatility_ratio(returns: Sequence[float]) -> float | None:
    if len(returns) < 8:
        return None
    long_volatility = pstdev(returns)
    short_window = max(4, len(returns) // 4)
    short_volatility = pstdev(returns[-short_window:])
    if long_volatility <= 0.0:
        return None
    return short_volatility / long_volatility


def _lag_one_correlation(values: Sequence[float]) -> float | None:
    if len(values) < 4:
        return None
    left = values[:-1]
    right = values[1:]
    left_std = pstdev(left)
    right_std = pstdev(right)
    if left_std <= 0.0 or right_std <= 0.0:
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    covariance = mean((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    return covariance / (left_std * right_std)
