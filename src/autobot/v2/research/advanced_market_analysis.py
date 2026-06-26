"""Advanced market-analysis signals for AUTOBOT research.

This module produces descriptive market context only.  It consumes local OHLCV
bars and optional research microstructure profiles; it never imports runtime
trading, paper execution, Kraken clients, or persistence layers.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import mean, pstdev
from typing import Any, Iterable, Mapping, Sequence

from .fractal_features import build_fractal_volatility_features
from .market_data_repository import MarketBar


@dataclass(frozen=True)
class AdvancedMarketAnalysisSnapshot:
    symbol: str
    timeframe: str
    timestamp: str | None
    sample_count: int
    volatility_regime_signal: str
    trend_regime_signal: str
    mean_reversion_regime_signal: str
    fractal_market_state: str
    turbulence_risk_score: float
    fat_tail_risk_score: float
    monte_carlo_survival_score: float
    cost_survival_score: float
    liquidity_risk_score: float
    overfitting_risk_score: float
    relative_value_state: str
    market_confidence_score: float
    details: Mapping[str, Any]
    research_only: bool = True
    execution_authority: str = "none"
    paper_candidate_allowed: bool = False
    live_promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["details"] = dict(self.details)
        payload["research_only"] = True
        payload["execution_authority"] = "none"
        payload["paper_candidate_allowed"] = False
        payload["live_promotion_allowed"] = False
        return payload


def build_advanced_market_analysis_snapshots(
    bars: Iterable[MarketBar],
    *,
    microstructure_profiles: Iterable[Mapping[str, Any]] = (),
    robustness: Mapping[str, Any] | None = None,
    deflated_sharpe: Mapping[str, Any] | None = None,
    relative_value_states: Mapping[str, str] | None = None,
    preferred_timeframe: str = "1h",
) -> tuple[AdvancedMarketAnalysisSnapshot, ...]:
    """Build one observation-only snapshot per symbol/timeframe."""

    rows = sorted(tuple(bars), key=lambda item: (item.symbol, item.timeframe, item.timestamp))
    grouped: dict[tuple[str, str], list[MarketBar]] = {}
    for bar in rows:
        grouped.setdefault((bar.symbol.upper(), str(bar.timeframe)), []).append(bar)
    fractal_by_key = {
        (item.symbol.upper(), item.timeframe): item.to_dict()
        for item in build_fractal_volatility_features(rows, preferred_timeframe=preferred_timeframe)
    }
    micro_by_symbol = {
        str(profile.get("symbol") or "").upper(): dict(profile)
        for profile in microstructure_profiles
        if profile.get("symbol")
    }
    snapshots = [
        _snapshot_for_group(
            symbol=symbol,
            timeframe=timeframe,
            bars=items,
            fractal=fractal_by_key.get((symbol, timeframe)) or _fallback_fractal(fractal_by_key, symbol),
            microstructure=micro_by_symbol.get(symbol),
            robustness=robustness,
            deflated_sharpe=deflated_sharpe,
            relative_value_state=(relative_value_states or {}).get(symbol, "not_available"),
        )
        for (symbol, timeframe), items in grouped.items()
    ]
    return tuple(sorted(snapshots, key=lambda item: (item.symbol, _timeframe_rank(item.timeframe), item.timeframe)))


def preferred_market_context_by_symbol(
    snapshots: Iterable[AdvancedMarketAnalysisSnapshot],
    *,
    preferred_order: Sequence[str] = ("1h", "15m", "5m", "4h"),
) -> dict[str, AdvancedMarketAnalysisSnapshot]:
    """Return the best available context per symbol for meta-scoring."""

    result: dict[str, AdvancedMarketAnalysisSnapshot] = {}
    rank = {timeframe: index for index, timeframe in enumerate(preferred_order)}
    for snapshot in snapshots:
        existing = result.get(snapshot.symbol)
        if existing is None:
            result[snapshot.symbol] = snapshot
            continue
        if rank.get(snapshot.timeframe, 999) < rank.get(existing.timeframe, 999):
            result[snapshot.symbol] = snapshot
        elif snapshot.timeframe == existing.timeframe and snapshot.sample_count > existing.sample_count:
            result[snapshot.symbol] = snapshot
    return result


def _snapshot_for_group(
    *,
    symbol: str,
    timeframe: str,
    bars: Sequence[MarketBar],
    fractal: Mapping[str, Any] | None,
    microstructure: Mapping[str, Any] | None,
    robustness: Mapping[str, Any] | None,
    deflated_sharpe: Mapping[str, Any] | None,
    relative_value_state: str,
) -> AdvancedMarketAnalysisSnapshot:
    ordered = sorted(bars, key=lambda item: item.timestamp)
    prices = [float(bar.close) for bar in ordered if bar.close > 0.0]
    returns = [math.log(right / left) for left, right in zip(prices, prices[1:]) if left > 0.0 and right > 0.0]
    sample_count = len(prices)
    timestamp = ordered[-1].timestamp.isoformat() if ordered else None
    volatility_bps = pstdev(returns) * 10_000.0 if len(returns) >= 2 else None
    volatility_ratio = _short_to_long_volatility_ratio(returns)
    trend_return_bps = _trend_return_bps(prices)
    zscore = _price_zscore(prices)
    kurtosis = _kurtosis(returns) if len(returns) >= 4 else None
    max_abs_return_bps = max((abs(value) * 10_000.0 for value in returns), default=0.0)

    volatility_signal = _volatility_signal(sample_count, volatility_bps, volatility_ratio)
    trend_signal = _trend_signal(sample_count, trend_return_bps, prices)
    fractal_state = str((fractal or {}).get("regime_hint") or "insufficient_data")
    mean_reversion_signal = _mean_reversion_signal(sample_count, zscore, trend_signal, fractal_state)
    turbulence = _turbulence_score(volatility_bps, max_abs_return_bps, volatility_ratio)
    fat_tail = _fat_tail_score(kurtosis, max_abs_return_bps, volatility_bps)
    liquidity = _liquidity_risk_score(microstructure)
    mc_survival = _monte_carlo_survival_score(robustness)
    overfit = _overfitting_risk_score(deflated_sharpe)
    cost_survival = _cost_survival_score(liquidity, volatility_bps, robustness)
    confidence = _market_confidence(
        sample_count=sample_count,
        volatility_signal=volatility_signal,
        trend_signal=trend_signal,
        mean_reversion_signal=mean_reversion_signal,
        turbulence=turbulence,
        fat_tail=fat_tail,
        liquidity=liquidity,
        cost_survival=cost_survival,
        overfit=overfit,
    )
    return AdvancedMarketAnalysisSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        sample_count=sample_count,
        volatility_regime_signal=volatility_signal,
        trend_regime_signal=trend_signal,
        mean_reversion_regime_signal=mean_reversion_signal,
        fractal_market_state=fractal_state,
        turbulence_risk_score=round(turbulence, 6),
        fat_tail_risk_score=round(fat_tail, 6),
        monte_carlo_survival_score=round(mc_survival, 6),
        cost_survival_score=round(cost_survival, 6),
        liquidity_risk_score=round(liquidity, 6),
        overfitting_risk_score=round(overfit, 6),
        relative_value_state=relative_value_state,
        market_confidence_score=round(confidence, 6),
        details={
            "volatility_bps": volatility_bps,
            "volatility_short_to_long_ratio": volatility_ratio,
            "trend_return_bps": trend_return_bps,
            "price_zscore": zscore,
            "return_kurtosis": kurtosis,
            "max_abs_return_bps": max_abs_return_bps,
            "microstructure": dict(microstructure or {}),
            "analysis_is_descriptive_not_predictive": True,
        },
    )


def _fallback_fractal(fractal_by_key: Mapping[tuple[str, str], Mapping[str, Any]], symbol: str) -> Mapping[str, Any] | None:
    for (candidate, _timeframe), payload in fractal_by_key.items():
        if candidate == symbol:
            return payload
    return None


def _volatility_signal(sample_count: int, volatility_bps: float | None, ratio: float | None) -> str:
    if sample_count < 16 or volatility_bps is None:
        return "insufficient_data"
    if volatility_bps < 8.0:
        return "low_activity"
    if volatility_bps >= 90.0:
        return "high_vol"
    if ratio is not None and ratio >= 1.50:
        return "volatility_expansion"
    if ratio is not None and ratio <= 0.65:
        return "volatility_compression"
    return "normal_volatility"


def _trend_signal(sample_count: int, trend_return_bps: float | None, prices: Sequence[float]) -> str:
    if sample_count < 24 or trend_return_bps is None:
        return "insufficient_data"
    short = mean(prices[-min(12, len(prices)) :])
    long = mean(prices[-min(48, len(prices)) :])
    if trend_return_bps >= 150.0 and short > long:
        return "trend_up"
    if trend_return_bps <= -150.0 and short < long:
        return "trend_down"
    return "range"


def _mean_reversion_signal(sample_count: int, zscore: float | None, trend_signal: str, fractal_state: str) -> str:
    if sample_count < 24 or zscore is None:
        return "insufficient_data"
    if abs(zscore) >= 1.25 and (trend_signal == "range" or fractal_state == "mean_reverting_like"):
        return "mean_reversion_favorable"
    if trend_signal in {"trend_up", "trend_down"} and abs(zscore) < 1.0:
        return "mean_reversion_unfavorable"
    return "mean_reversion_neutral"


def _turbulence_score(
    volatility_bps: float | None,
    max_abs_return_bps: float,
    ratio: float | None,
) -> float:
    if volatility_bps is None or volatility_bps <= 0.0:
        return 50.0
    shock_ratio = max_abs_return_bps / max(volatility_bps, 1e-12)
    return _clamp((shock_ratio - 1.0) * 18.0 + max(0.0, (ratio or 1.0) - 1.0) * 35.0, 0.0, 100.0)


def _fat_tail_score(
    kurtosis: float | None,
    max_abs_return_bps: float,
    volatility_bps: float | None,
) -> float:
    if kurtosis is None:
        return 50.0
    kurtosis_component = max(0.0, kurtosis - 3.0) * 18.0
    shock_component = 0.0
    if volatility_bps and volatility_bps > 0.0:
        shock_component = max(0.0, (max_abs_return_bps / volatility_bps) - 3.0) * 20.0
    return _clamp(kurtosis_component + shock_component, 0.0, 100.0)


def _liquidity_risk_score(profile: Mapping[str, Any] | None) -> float:
    if not profile:
        return 55.0
    status = str(profile.get("cost_risk_status") or "unknown")
    if status == "cheap":
        base = 15.0
    elif status == "normal":
        base = 35.0
    elif status == "expensive":
        base = 75.0
    elif status == "avoid":
        base = 95.0
    else:
        base = 55.0
    spread = _float(profile.get("p95_spread_bps"), 0.0)
    if spread >= 80.0:
        base = max(base, 90.0)
    elif spread >= 40.0:
        base = max(base, 70.0)
    return _clamp(base, 0.0, 100.0)


def _monte_carlo_survival_score(robustness: Mapping[str, Any] | None) -> float:
    if not robustness:
        return 50.0
    monte = dict(robustness.get("monte_carlo") or {})
    probability = _float(monte.get("probability_positive_net_pnl"), None)
    if probability is None:
        return 50.0
    return _clamp(probability * 100.0, 0.0, 100.0)


def _cost_survival_score(
    liquidity_risk: float,
    volatility_bps: float | None,
    robustness: Mapping[str, Any] | None,
) -> float:
    stress_bonus = 0.0
    stress = (robustness or {}).get("stress_scenarios") or ()
    if stress:
        positive = sum(1 for item in stress if _float((item.get("metrics") or {}).get("total_net_pnl_eur"), -1.0) > 0.0)
        stress_bonus = (positive / len(stress)) * 20.0
    volatility_component = 10.0 if volatility_bps is not None and volatility_bps >= 20.0 else -10.0
    return _clamp(80.0 - liquidity_risk + volatility_component + stress_bonus, 0.0, 100.0)


def _overfitting_risk_score(deflated_sharpe: Mapping[str, Any] | None) -> float:
    if not deflated_sharpe:
        return 60.0
    return _clamp(_float(deflated_sharpe.get("overfitting_risk_score"), 60.0), 0.0, 100.0)


def _market_confidence(
    *,
    sample_count: int,
    volatility_signal: str,
    trend_signal: str,
    mean_reversion_signal: str,
    turbulence: float,
    fat_tail: float,
    liquidity: float,
    cost_survival: float,
    overfit: float,
) -> float:
    structure = 45.0
    if trend_signal in {"trend_up", "trend_down"}:
        structure += 18.0
    elif trend_signal == "range" and mean_reversion_signal == "mean_reversion_favorable":
        structure += 12.0
    if volatility_signal in {"low_activity", "high_vol", "insufficient_data"}:
        structure -= 15.0
    confidence = (
        _clamp(structure, 0.0, 100.0) * 0.25
        + (100.0 - turbulence) * 0.18
        + (100.0 - fat_tail) * 0.14
        + (100.0 - liquidity) * 0.18
        + cost_survival * 0.15
        + (100.0 - overfit) * 0.10
    )
    if sample_count < 32:
        confidence = min(confidence, 35.0)
    return _clamp(confidence, 0.0, 100.0)


def _trend_return_bps(prices: Sequence[float]) -> float | None:
    if len(prices) < 8:
        return None
    left = prices[-min(48, len(prices))]
    right = prices[-1]
    if left <= 0.0:
        return None
    return (right / left - 1.0) * 10_000.0


def _price_zscore(prices: Sequence[float]) -> float | None:
    if len(prices) < 8:
        return None
    window = prices[-min(48, len(prices)) :]
    deviation = pstdev(window)
    if deviation <= 0.0:
        return None
    return (window[-1] - mean(window)) / deviation


def _short_to_long_volatility_ratio(returns: Sequence[float]) -> float | None:
    if len(returns) < 8:
        return None
    long_volatility = pstdev(returns)
    if long_volatility <= 0.0:
        return None
    short_window = max(4, len(returns) // 4)
    return pstdev(returns[-short_window:]) / long_volatility


def _kurtosis(values: Sequence[float]) -> float:
    deviation = pstdev(values)
    if deviation <= 0.0:
        return 3.0
    center = mean(values)
    return mean(((value - center) / deviation) ** 4 for value in values)


def _timeframe_rank(timeframe: str) -> int:
    return {"1h": 0, "4h": 1, "15m": 2, "5m": 3}.get(timeframe, 99)


def _float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))
