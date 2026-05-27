"""Outcome-backed pattern learning for AUTOBOT.

This module is intentionally observe-only by default. It groups labelled
decision outcomes into interpretable buckets so AUTOBOT can see which market
contexts have historically reached take-profit, stop-loss, or expired.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(float(raw)) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _bucket(value: float, cuts: tuple[tuple[float, str], ...], default: str) -> str:
    for limit, name in cuts:
        if value < limit:
            return name
    return default


def _bps_bucket(value: float, *, kind: str) -> str:
    if kind == "edge":
        return _bucket(value, ((0.0, "negative"), (12.0, "weak"), (35.0, "watch"), (80.0, "valid"), (160.0, "strong")), "very_strong")
    if kind == "cost":
        return _bucket(value, ((10.0, "low"), (25.0, "normal"), (50.0, "high"), (100.0, "very_high")), "extreme")
    if kind == "atr":
        return _bucket(value, ((5.0, "flat"), (18.0, "low"), (80.0, "tradable"), (220.0, "high")), "extreme")
    if kind == "spread":
        return _bucket(value, ((2.0, "tight"), (8.0, "normal"), (20.0, "wide")), "very_wide")
    return "unknown"


def _payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = row.get("payload")
    return payload if isinstance(payload, Mapping) else {}


def _decision_payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = _payload(row)
    decision = payload.get("decision_payload")
    return decision if isinstance(decision, Mapping) else {}


def _opportunity_payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    decision = _decision_payload(row)
    opportunity = decision.get("opportunity")
    return opportunity if isinstance(opportunity, Mapping) else {}


def _nested(mapping: Mapping[str, Any], *path: str) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _feature_value(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    decision = _decision_payload(row)
    opportunity = _opportunity_payload(row)
    if key in decision:
        return decision.get(key)
    if key in opportunity:
        return opportunity.get(key)
    edge_context = decision.get("edge_context") if isinstance(decision.get("edge_context"), Mapping) else {}
    aliases = {
        "gross_edge_bps": ("expected_move_bps",),
        "net_edge_bps": ("net_edge_bps",),
        "cost_bps": ("total_cost_bps",),
        "spread_bps": ("spread_bps",),
        "min_edge_bps": ("adaptive_min_edge_bps",),
    }
    for alias in aliases.get(key, ()):
        if alias in edge_context:
            return edge_context.get(alias)
    return default


def _regime(row: Mapping[str, Any]) -> str:
    opportunity = _opportunity_payload(row)
    regime = _nested(opportunity, "regime_context", "regime")
    return str(regime or "unknown")


def _health_status(row: Mapping[str, Any]) -> str:
    opportunity = _opportunity_payload(row)
    status = _nested(opportunity, "health_context", "status")
    return str(status or "unknown")


def extract_pattern_features(row: Mapping[str, Any]) -> dict[str, Any]:
    gross = _safe_float(row.get("gross_return_bps"), _safe_float(_feature_value(row, "gross_edge_bps")))
    cost = _safe_float(row.get("estimated_cost_bps"), _safe_float(_feature_value(row, "cost_bps")))
    net = _safe_float(row.get("net_return_bps"), _safe_float(_feature_value(row, "net_edge_bps")))
    atr_pct = _safe_float(_feature_value(row, "atr_pct"))
    atr_bps = _safe_float(_feature_value(row, "atr_bps"), atr_pct * 10000.0 if atr_pct else 0.0)
    spread = _safe_float(_feature_value(row, "spread_bps"))
    opportunity = _opportunity_payload(row)
    return {
        "symbol": str(row.get("symbol") or "UNKNOWN").upper(),
        "engine": str(row.get("engine") or row.get("strategy") or "unknown"),
        "strategy": str(row.get("strategy") or "unknown"),
        "reason": str(row.get("rejection_reason") or row.get("original_status") or "accepted"),
        "horizon": str(row.get("horizon_minutes") or "unknown"),
        "source": str(row.get("source") or "unknown"),
        "barrier": str(_payload(row).get("barrier_touched") or "unknown"),
        "regime": _regime(row),
        "health_status": _health_status(row),
        "gross_edge_bucket": _bps_bucket(gross, kind="edge"),
        "net_edge_bucket": _bps_bucket(net, kind="edge"),
        "cost_bucket": _bps_bucket(cost, kind="cost"),
        "atr_bucket": _bps_bucket(atr_bps, kind="atr"),
        "spread_bucket": _bps_bucket(spread, kind="spread"),
        "opportunity_status": str(opportunity.get("status") or "unknown"),
        "opportunity_reason": str(opportunity.get("reason") or "unknown"),
    }


@dataclass(frozen=True)
class PatternLearningConfig:
    enabled: bool = True
    observe_only: bool = True
    min_samples: int = 8
    max_outcomes: int = 1000
    good_threshold_bps: float = 35.0
    bad_threshold_bps: float = -35.0
    prefer_triple_barrier: bool = True

    @classmethod
    def from_env(cls) -> "PatternLearningConfig":
        return cls(
            enabled=_env_bool("PATTERN_LEARNING_ENABLED", True),
            observe_only=_env_bool("PATTERN_LEARNING_OBSERVE_ONLY", True),
            min_samples=_env_int("PATTERN_LEARNING_MIN_SAMPLES", 8, 2, 10_000),
            max_outcomes=_env_int("PATTERN_LEARNING_MAX_OUTCOMES", 1000, 10, 100_000),
            good_threshold_bps=_env_float("PATTERN_LEARNING_GOOD_BPS", 35.0, 1.0, 10_000.0),
            bad_threshold_bps=-_env_float("PATTERN_LEARNING_BAD_BPS", 35.0, 1.0, 10_000.0),
            prefer_triple_barrier=_env_bool("PATTERN_LEARNING_PREFER_TRIPLE_BARRIER", True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "observe_only": self.observe_only,
            "min_samples": self.min_samples,
            "max_outcomes": self.max_outcomes,
            "good_threshold_bps": self.good_threshold_bps,
            "bad_threshold_bps": self.bad_threshold_bps,
            "prefer_triple_barrier": self.prefer_triple_barrier,
        }


class PatternLearningEngine:
    """Aggregate post-decision outcomes into interpretable pattern statistics."""

    def __init__(self, config: Optional[PatternLearningConfig] = None) -> None:
        self.config = config or PatternLearningConfig.from_env()

    def build_snapshot(self, outcomes: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        rows = [row for row in outcomes or [] if isinstance(row, Mapping)]
        if self.config.prefer_triple_barrier:
            triple_rows = [row for row in rows if str(row.get("source") or "") == "decision_learning_triple_barrier"]
            if triple_rows:
                rows = triple_rows
        patterns = self._patterns(rows)
        ranked = sorted(patterns.values(), key=lambda item: (item["confidence"], item["samples"]), reverse=True)
        reliable = [row for row in ranked if row["samples"] >= self.config.min_samples]
        positive = [row for row in reliable if row["status"] == "positive_pattern"]
        negative = [row for row in reliable if row["status"] == "negative_pattern"]
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "enabled": self.config.enabled,
            "mode": "observe_only" if self.config.observe_only else "score_ready",
            "config": self.config.to_dict(),
            "summary": {
                "outcomes_used": len(rows),
                "patterns": len(ranked),
                "reliable_patterns": len(reliable),
                "positive_patterns": len(positive),
                "negative_patterns": len(negative),
            },
            "top_positive": positive[:10],
            "top_negative": negative[:10],
            "patterns": ranked[:50],
            "safety": {
                "writes_orders": False,
                "changes_thresholds": False,
                "live_promotion": False,
                "uses_future_data_for_live_decision": False,
            },
        }

    def _patterns(self, rows: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
        patterns: dict[str, dict[str, Any]] = {}
        for row in rows:
            features = extract_pattern_features(row)
            groups = self._groups(features)
            for group_name, parts in groups:
                key = "|".join([group_name, *[f"{name}={features.get(name)}" for name in parts]])
                item = patterns.setdefault(
                    key,
                    {
                        "pattern_id": key,
                        "group": group_name,
                        "features": {name: features.get(name) for name in parts},
                        "samples": 0,
                        "good": 0,
                        "bad": 0,
                        "neutral": 0,
                        "avg_net_return_bps": 0.0,
                        "avg_gross_return_bps": 0.0,
                        "sources": {},
                        "symbols": {},
                    },
                )
                self._add_row(item, row, features)
        for item in patterns.values():
            samples = max(1, int(item["samples"]))
            item["avg_net_return_bps"] = round(float(item["avg_net_return_bps"]) / samples, 3)
            item["avg_gross_return_bps"] = round(float(item["avg_gross_return_bps"]) / samples, 3)
            item["win_rate"] = round(float(item["good"]) / samples, 4)
            item["loss_rate"] = round(float(item["bad"]) / samples, 4)
            item["confidence"] = self._confidence(item)
            item["status"] = self._status(item)
            item["reason"] = self._reason(item)
        return patterns

    @staticmethod
    def _groups(features: Mapping[str, Any]) -> list[tuple[str, tuple[str, ...]]]:
        return [
            ("symbol_engine_regime", ("symbol", "engine", "regime")),
            ("engine_regime_setup", ("engine", "regime", "net_edge_bucket", "atr_bucket")),
            ("rejection_context", ("reason", "regime", "net_edge_bucket", "atr_bucket")),
            ("cost_edge_context", ("net_edge_bucket", "cost_bucket", "spread_bucket")),
            ("health_context", ("engine", "health_status", "opportunity_reason")),
        ]

    def _add_row(self, item: dict[str, Any], row: Mapping[str, Any], features: Mapping[str, Any]) -> None:
        net = _safe_float(row.get("net_return_bps"))
        gross = _safe_float(row.get("gross_return_bps"))
        label = str(row.get("outcome_label") or "")
        barrier = str(features.get("barrier") or "")
        item["samples"] += 1
        item["avg_net_return_bps"] += net
        item["avg_gross_return_bps"] += gross
        if self._is_good(label, barrier, net):
            item["good"] += 1
        elif self._is_bad(label, barrier, net):
            item["bad"] += 1
        else:
            item["neutral"] += 1
        source = str(row.get("source") or "unknown")
        symbol = str(row.get("symbol") or "UNKNOWN")
        item["sources"][source] = item["sources"].get(source, 0) + 1
        item["symbols"][symbol] = item["symbols"].get(symbol, 0) + 1

    def _is_good(self, label: str, barrier: str, net_return_bps: float) -> bool:
        return (
            label in {"accepted_positive", "missed_profit"}
            or barrier == "take_profit"
            or net_return_bps >= self.config.good_threshold_bps
        )

    def _is_bad(self, label: str, barrier: str, net_return_bps: float) -> bool:
        return (
            label in {"accepted_negative", "saved_loss"}
            or barrier == "stop_loss"
            or net_return_bps <= self.config.bad_threshold_bps
        )

    def _confidence(self, item: Mapping[str, Any]) -> float:
        samples = max(1, int(item.get("samples") or 0))
        good = int(item.get("good") or 0)
        bad = int(item.get("bad") or 0)
        evidence = min(1.0, samples / max(1, self.config.min_samples * 3))
        edge = (good - bad) / samples
        return round(max(0.0, min(1.0, 0.5 + (edge * 0.5))) * evidence, 4)

    def _status(self, item: Mapping[str, Any]) -> str:
        samples = int(item.get("samples") or 0)
        if samples < self.config.min_samples:
            return "learning"
        avg_net = _safe_float(item.get("avg_net_return_bps"))
        win_rate = _safe_float(item.get("win_rate"))
        loss_rate = _safe_float(item.get("loss_rate"))
        if avg_net >= self.config.good_threshold_bps and win_rate > loss_rate:
            return "positive_pattern"
        if avg_net <= self.config.bad_threshold_bps and loss_rate >= win_rate:
            return "negative_pattern"
        return "mixed_pattern"

    def _reason(self, item: Mapping[str, Any]) -> str:
        status = str(item.get("status") or "learning")
        if status == "learning":
            return "insufficient_labelled_outcomes"
        if status == "positive_pattern":
            return "historically_reached_profit_barrier_more_often"
        if status == "negative_pattern":
            return "historically_reached_loss_barrier_or_negative_net"
        return "mixed_or_not_statistically_clear"
