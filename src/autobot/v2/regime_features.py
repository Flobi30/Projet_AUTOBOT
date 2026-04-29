"""Lightweight Markov/entropy regime features for opportunity scoring."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence


REGIME_STATES = ("DOWN", "FLAT", "UP", "VOLATILE")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


@dataclass(frozen=True)
class RegimeFeatureConfig:
    enabled: bool = True
    entropy_window: int = 64
    markov_window: int = 96
    min_samples: int = 32
    high_entropy_threshold: float = 0.78
    low_entropy_threshold: float = 0.45
    score_weight: float = 8.0
    flat_return_bps: float = 3.0
    volatile_return_bps: float = 30.0

    @classmethod
    def from_env(cls) -> "RegimeFeatureConfig":
        return cls(
            enabled=_env_bool("REGIME_SCORING_ENABLED", True),
            entropy_window=_env_int("REGIME_ENTROPY_WINDOW", 64, 8, 1000),
            markov_window=_env_int("REGIME_MARKOV_WINDOW", 96, 8, 2000),
            min_samples=_env_int("REGIME_MIN_SAMPLES", 32, 4, 1000),
            high_entropy_threshold=_env_float("REGIME_HIGH_ENTROPY_THRESHOLD", 0.78, 0.0, 1.0),
            low_entropy_threshold=_env_float("REGIME_LOW_ENTROPY_THRESHOLD", 0.45, 0.0, 1.0),
            score_weight=_env_float("REGIME_SCORE_WEIGHT", 8.0, 0.0, 25.0),
            flat_return_bps=_env_float("REGIME_FLAT_RETURN_BPS", 3.0, 0.0, 1000.0),
            volatile_return_bps=_env_float("REGIME_VOLATILE_RETURN_BPS", 30.0, 0.1, 5000.0),
        )


@dataclass
class RegimeFeatureResult:
    symbol: str
    regime: str
    confidence: float
    entropy_norm: float
    markov_state: str
    persistence_probability: float
    sample_count: int
    regime_score: float
    reason: str
    transition_matrix: dict[str, dict[str, float]] = field(default_factory=dict)
    state_distribution: dict[str, float] = field(default_factory=dict)
    adjustment: float = 0.0
    enabled: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "regime": self.regime,
            "confidence": round(self.confidence, 4),
            "entropy_norm": round(self.entropy_norm, 4),
            "markov_state": self.markov_state,
            "persistence_probability": round(self.persistence_probability, 4),
            "sample_count": self.sample_count,
            "regime_score": round(self.regime_score, 2),
            "reason": self.reason,
            "transition_matrix": {
                src: {dst: round(prob, 4) for dst, prob in row.items()}
                for src, row in self.transition_matrix.items()
            },
            "state_distribution": {k: round(v, 4) for k, v in self.state_distribution.items()},
            "adjustment": round(self.adjustment, 3),
            "enabled": self.enabled,
            "timestamp": self.timestamp,
        }


class RegimeFeatureEngine:
    """Compute entropy and simple Markov state features from price history."""

    def __init__(self, config: RegimeFeatureConfig | None = None) -> None:
        self.config = config or RegimeFeatureConfig.from_env()

    def analyze_symbol(self, symbol: str, price_history: Iterable[Any] | None) -> RegimeFeatureResult:
        prices = self._extract_prices(price_history)
        if not self.config.enabled:
            return self._neutral(symbol, len(prices), "disabled", enabled=False)

        returns_bps = self._log_returns_bps(prices)
        sample_count = len(returns_bps)
        if sample_count < self.config.min_samples:
            return self._neutral(symbol, sample_count, "insufficient_samples")

        entropy_returns = returns_bps[-self.config.entropy_window :]
        markov_returns = returns_bps[-self.config.markov_window :]
        states = [self._state_from_return(ret) for ret in markov_returns]
        entropy_norm = self._normalized_entropy([self._state_from_return(ret) for ret in entropy_returns])
        transition_matrix = self._transition_matrix(states)
        distribution = self._state_distribution(states)
        markov_state = states[-1] if states else "FLAT"
        persistence = transition_matrix.get(markov_state, {}).get(markov_state, 0.0)

        regime, score, reason = self._classify_regime(
            states=states,
            returns_bps=markov_returns,
            entropy_norm=entropy_norm,
            persistence=persistence,
        )
        confidence = self._confidence(
            sample_count=sample_count,
            distribution=distribution,
            persistence=persistence,
            entropy_norm=entropy_norm,
            regime=regime,
        )
        adjustment = self.adjustment_for_score(score)

        return RegimeFeatureResult(
            symbol=symbol,
            regime=regime,
            confidence=confidence,
            entropy_norm=entropy_norm,
            markov_state=markov_state,
            persistence_probability=persistence,
            sample_count=sample_count,
            regime_score=score,
            reason=reason,
            transition_matrix=transition_matrix,
            state_distribution=distribution,
            adjustment=adjustment,
            enabled=True,
        )

    def analyze_instance(self, instance: Mapping[str, Any]) -> RegimeFeatureResult:
        symbol = str(instance.get("symbol") or instance.get("pair") or "UNKNOWN")
        history = instance.get("price_history_tail") or instance.get("price_history") or []
        return self.analyze_symbol(symbol, history)

    def build_snapshot(
        self,
        *,
        instances: Iterable[Mapping[str, Any]],
        paper_mode: bool,
    ) -> dict[str, Any]:
        rows = [self.analyze_instance(inst).to_dict() for inst in instances]
        rows.sort(key=lambda item: item.get("regime_score", 0.0), reverse=True)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "paper" if paper_mode else "live",
            "paper_mode": paper_mode,
            "config": {
                "enabled": self.config.enabled,
                "entropy_window": self.config.entropy_window,
                "markov_window": self.config.markov_window,
                "min_samples": self.config.min_samples,
                "high_entropy_threshold": self.config.high_entropy_threshold,
                "low_entropy_threshold": self.config.low_entropy_threshold,
                "score_weight": self.config.score_weight,
                "flat_return_bps": self.config.flat_return_bps,
                "volatile_return_bps": self.config.volatile_return_bps,
            },
            "symbols": rows,
        }

    def adjustment_for_score(self, regime_score: float) -> float:
        if not self.config.enabled or self.config.score_weight <= 0.0:
            return 0.0
        normalized = _clamp((regime_score - 50.0) / 50.0, -1.0, 1.0)
        return max(-self.config.score_weight, min(self.config.score_weight, normalized * self.config.score_weight))

    def neutral_result(self, symbol: str, sample_count: int = 0, reason: str = "unavailable") -> RegimeFeatureResult:
        return self._neutral(symbol, sample_count, reason)

    def _neutral(
        self,
        symbol: str,
        sample_count: int,
        reason: str,
        *,
        enabled: bool = True,
    ) -> RegimeFeatureResult:
        return RegimeFeatureResult(
            symbol=symbol,
            regime="unknown",
            confidence=0.0 if sample_count == 0 else min(0.35, sample_count / max(self.config.min_samples, 1) * 0.35),
            entropy_norm=0.0,
            markov_state="UNKNOWN",
            persistence_probability=0.0,
            sample_count=sample_count,
            regime_score=50.0,
            reason=reason,
            transition_matrix={state: {dst: 0.0 for dst in REGIME_STATES} for state in REGIME_STATES},
            state_distribution={state: 0.0 for state in REGIME_STATES},
            adjustment=0.0,
            enabled=enabled,
        )

    def _classify_regime(
        self,
        *,
        states: Sequence[str],
        returns_bps: Sequence[float],
        entropy_norm: float,
        persistence: float,
    ) -> tuple[str, float, str]:
        distribution = self._state_distribution(states)
        flat_ratio = distribution.get("FLAT", 0.0)
        up_ratio = distribution.get("UP", 0.0)
        down_ratio = distribution.get("DOWN", 0.0)
        volatile_ratio = distribution.get("VOLATILE", 0.0)
        directional_ratio = max(up_ratio, down_ratio)
        mean_abs = sum(abs(ret) for ret in returns_bps) / max(len(returns_bps), 1)

        if entropy_norm >= self.config.high_entropy_threshold and persistence < 0.55:
            return "chaos", 25.0, "high_entropy_low_persistence"
        if volatile_ratio >= 0.30 or mean_abs >= self.config.volatile_return_bps * 0.75:
            return "high_vol", 48.0, "volatile_returns"
        if mean_abs <= max(self.config.flat_return_bps * 0.55, 0.1) and entropy_norm <= self.config.low_entropy_threshold:
            return "low_activity", 44.0, "low_activity"
        if flat_ratio >= 0.45 and entropy_norm <= self.config.high_entropy_threshold:
            score = 82.0 if persistence >= 0.45 else 74.0
            reason = "range_stable" if persistence >= 0.45 else "range_mixed"
            return "range", score, reason
        if directional_ratio >= 0.55 and entropy_norm <= self.config.high_entropy_threshold:
            return "trend", 65.0, "directional_persistence"
        if entropy_norm >= self.config.high_entropy_threshold:
            return "chaos", 32.0, "high_entropy"
        return "range", 58.0, "mixed_range"

    def _confidence(
        self,
        *,
        sample_count: int,
        distribution: Mapping[str, float],
        persistence: float,
        entropy_norm: float,
        regime: str,
    ) -> float:
        sample_conf = _clamp(sample_count / max(self.config.min_samples * 2.0, 1.0))
        dominant = max(distribution.values()) if distribution else 0.0
        entropy_fit = 1.0 - entropy_norm if regime in {"range", "low_activity"} else entropy_norm
        raw = 0.20 + 0.35 * persistence + 0.25 * dominant + 0.20 * _clamp(entropy_fit)
        return _clamp(raw * sample_conf)

    def _state_from_return(self, return_bps: float) -> str:
        abs_bps = abs(return_bps)
        if abs_bps >= self.config.volatile_return_bps:
            return "VOLATILE"
        if abs_bps <= self.config.flat_return_bps:
            return "FLAT"
        return "UP" if return_bps > 0.0 else "DOWN"

    @staticmethod
    def _normalized_entropy(states: Sequence[str]) -> float:
        if not states:
            return 0.0
        counts = {state: states.count(state) for state in REGIME_STATES}
        total = float(len(states))
        entropy = 0.0
        for count in counts.values():
            if count <= 0:
                continue
            probability = count / total
            entropy -= probability * math.log(probability)
        return _clamp(entropy / math.log(len(REGIME_STATES)))

    @staticmethod
    def _transition_matrix(states: Sequence[str]) -> dict[str, dict[str, float]]:
        counts = {src: {dst: 0 for dst in REGIME_STATES} for src in REGIME_STATES}
        for src, dst in zip(states, states[1:]):
            if src in counts and dst in counts[src]:
                counts[src][dst] += 1
        matrix: dict[str, dict[str, float]] = {}
        for src, row in counts.items():
            total = float(sum(row.values()))
            matrix[src] = {
                dst: (count / total if total > 0.0 else 0.0)
                for dst, count in row.items()
            }
        return matrix

    @staticmethod
    def _state_distribution(states: Sequence[str]) -> dict[str, float]:
        total = float(len(states))
        if total <= 0.0:
            return {state: 0.0 for state in REGIME_STATES}
        return {state: states.count(state) / total for state in REGIME_STATES}

    @staticmethod
    def _log_returns_bps(prices: Sequence[float]) -> list[float]:
        returns: list[float] = []
        for prev, current in zip(prices, prices[1:]):
            if prev <= 0.0 or current <= 0.0:
                continue
            returns.append(math.log(current / prev) * 10000.0)
        return returns

    @staticmethod
    def _extract_prices(price_history: Iterable[Any] | None) -> list[float]:
        prices: list[float] = []
        for item in price_history or []:
            value: Any
            if isinstance(item, Mapping):
                value = item.get("price")
            elif isinstance(item, (tuple, list)) and item:
                value = item[-1]
            else:
                value = item
            try:
                price = float(value)
            except (TypeError, ValueError):
                continue
            if price > 0.0 and math.isfinite(price):
                prices.append(price)
        return prices
