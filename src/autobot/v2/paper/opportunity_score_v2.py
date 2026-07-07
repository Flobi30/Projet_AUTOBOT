"""Research-only opportunity score v2.

The v2 score is a metadata/research score only. It is designed to make
pre-trade high-conviction context visible without replacing the runtime router
score or authorizing paper/live execution.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from autobot.v2.paper.forward_edge_simulation import LookaheadInputError


SCORE_V2_VERSION = "opportunity_score_v2_research_2026_07"
HIGH_THRESHOLD = 70.0
MEDIUM_THRESHOLD = 40.0
SCORE_V2_BUCKETS = ("high", "medium", "low", "missing")

FORBIDDEN_SCORE_V2_KEYS = frozenset(
    {
        "closed_at",
        "closing_decision",
        "closing_leg",
        "exit",
        "exit_price",
        "exit_reason",
        "future_close",
        "gross_pnl",
        "gross_pnl_eur",
        "mae_bps",
        "mfe_bps",
        "net_pnl",
        "net_pnl_eur",
        "outcome",
        "post_trade_bucket",
        "realized_pnl",
        "trade_result",
    }
)
FORBIDDEN_SCORE_V2_CONTAINER_KEYS = frozenset({"closing_decision", "closing_leg"})

COMPONENT_WEIGHTS: dict[str, float] = {
    "expected_net_edge": 22.0,
    "risk_reward": 14.0,
    "breakout_quality": 10.0,
    "trend_quality": 10.0,
    "volatility_expansion": 8.0,
    "support_resistance": 8.0,
    "spread_liquidity": 10.0,
    "pair_health": 6.0,
    "segment_health": 6.0,
    "cost_pressure": 6.0,
}
REQUIRED_COMPONENTS = ("expected_move_bps", "estimated_total_cost_bps")


@dataclass(frozen=True)
class OpportunityScoreV2Result:
    score: float | None
    bucket: str
    components: dict[str, float | None]
    missing_components: tuple[str, ...]
    reason: str
    version: str = SCORE_V2_VERSION
    research_only: bool = True
    shadow_only: bool = True
    promotable: bool = False
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    uses_future_data: bool = False

    def to_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "score_v2_bucket": self.bucket,
            "score_v2_components": dict(self.components),
            "score_v2_reason": self.reason,
            "score_v2_version": self.version,
            "score_v2_research_only": self.research_only,
            "score_v2_shadow_only": self.shadow_only,
            "score_v2_promotable": self.promotable,
            "score_v2_paper_capital_allowed": self.paper_capital_allowed,
            "score_v2_live_allowed": self.live_allowed,
            "score_v2_uses_future_data": self.uses_future_data,
            "score_v2_missing_components": list(self.missing_components),
        }
        if self.score is not None:
            metadata["opportunity_score_v2"] = self.score
        return metadata

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_opportunity_score_v2_metadata(source: Mapping[str, Any]) -> dict[str, Any]:
    """Return ledger/report metadata for the research-only v2 score."""

    return calculate_opportunity_score_v2(source).to_metadata()


def calculate_opportunity_score_v2(source: Mapping[str, Any]) -> OpportunityScoreV2Result:
    """Calculate the v2 score from pre-entry fields only.

    Missing mandatory pre-entry inputs produce a ``missing`` bucket. Post-trade
    fields raise ``LookaheadInputError`` so tests can enforce the contract.
    """

    _audit_no_lookahead(source)
    expected_move = _first_float(source, ("expected_move_bps", "expected_gross_move_bps", "target_move_bps"))
    total_cost = _first_float(
        source,
        (
            "estimated_total_cost_bps",
            "estimated_round_trip_cost_bps",
            "total_cost_bps",
            "round_trip_cost_bps",
            "cost_bps",
        ),
    )
    missing: list[str] = []
    if expected_move is None:
        missing.append("expected_move_bps")
    if total_cost is None:
        missing.append("estimated_total_cost_bps")
    if missing:
        return OpportunityScoreV2Result(
            score=None,
            bucket="missing",
            components=_empty_components(),
            missing_components=tuple(missing),
            reason="insufficient_pretrade_expected_move_or_cost",
        )

    assert expected_move is not None
    assert total_cost is not None
    fees = _first_float(source, ("estimated_fees_bps", "fees_bps", "round_trip_fee_bps"))
    spread = _first_float(source, ("estimated_spread_cost_bps", "spread_bps", "spread_cost_bps"))
    slippage = _first_float(source, ("estimated_slippage_bps", "slippage_cost_bps", "expected_slippage_bps"))
    latency = _first_float(source, ("latency_buffer_bps", "latency_bps"))
    risk_penalties = _safe_float(source, "risk_penalties_bps") + _safe_float(source, "drawdown_penalty_bps")
    risk_penalties += _safe_float(source, "trade_frequency_penalty_bps")

    explicit_net_edge = _first_float(
        source,
        ("estimated_net_edge_bps", "expected_net_edge_bps", "net_edge_bps", "edge_after_cost_bps"),
    )
    estimated_net_edge = explicit_net_edge
    if estimated_net_edge is None:
        estimated_net_edge = expected_move - total_cost - risk_penalties

    logical_stop = _first_float(source, ("logical_stop_bps", "stop_loss_bps", "risk_bps"))
    rr = _first_float(source, ("risk_reward_ratio", "risk_reward", "rr", "tp_sl_ratio"))
    if rr is None and logical_stop and logical_stop > 0.0:
        rr = expected_move / logical_stop

    components: dict[str, float | None] = {
        "expected_net_edge": _score_expected_net_edge(expected_move, total_cost, estimated_net_edge),
        "risk_reward": _score_risk_reward(rr),
        "breakout_quality": _score_alias(source, ("breakout_quality", "breakout_score", "breakout_strength")),
        "trend_quality": _score_alias(
            source,
            ("trend_quality", "trend_score", "trend_strength", "trend_timeframe_alignment", "multi_timeframe_alignment"),
        ),
        "volatility_expansion": _score_alias(
            source,
            ("volatility_expansion", "volatility_expansion_score", "atr_expansion_bps", "volatility_score"),
        ),
        "support_resistance": _score_alias(
            source,
            ("support_resistance", "support_strength", "support_distance_quality", "sr_score"),
        ),
        "spread_liquidity": _score_spread_liquidity(source, expected_move, spread, slippage),
        "pair_health": _score_health(source, "pair"),
        "segment_health": _score_health(source, "segment"),
        "cost_pressure": _score_cost_pressure(expected_move, total_cost, fees, spread, slippage, latency),
    }
    component_missing = tuple(name for name, value in components.items() if value is None)
    score = 0.0
    for name, weight in COMPONENT_WEIGHTS.items():
        value = components.get(name)
        if value is not None:
            score += value * weight
    if estimated_net_edge <= 0.0:
        score -= min(30.0, abs(estimated_net_edge) / 5.0 + 10.0)
    if risk_penalties > 0.0:
        score -= min(20.0, risk_penalties / 2.0)
    score = _clamp_score(score)
    reason = _reason(score, component_missing, estimated_net_edge)
    return OpportunityScoreV2Result(
        score=score,
        bucket=score_v2_bucket(score),
        components=components,
        missing_components=component_missing,
        reason=reason,
    )


def score_v2_bucket(score: float | None) -> str:
    if score is None:
        return "missing"
    if score >= HIGH_THRESHOLD:
        return "high"
    if score >= MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def _score_expected_net_edge(expected_move: float, total_cost: float, estimated_net_edge: float) -> float:
    move_quality = _clamp(expected_move / 500.0)
    edge_quality = _clamp(estimated_net_edge / 300.0)
    cost_efficiency = _clamp(1.0 - max(total_cost, 0.0) / max(expected_move, 1.0))
    return _clamp((move_quality * 0.30) + (edge_quality * 0.45) + (cost_efficiency * 0.25))


def _score_risk_reward(rr: float | None) -> float | None:
    if rr is None:
        return None
    if rr <= 0.0:
        return 0.0
    return _clamp((rr - 1.0) / 2.0)


def _score_spread_liquidity(
    source: Mapping[str, Any],
    expected_move: float,
    spread: float | None,
    slippage: float | None,
) -> float | None:
    explicit = _score_alias(source, ("liquidity_score", "depth_score", "spread_liquidity_score"))
    if explicit is not None:
        return explicit
    spread_value = spread
    if spread_value is None:
        spread_value = _first_float(source, ("spread_bps", "estimated_spread_bps"))
    total = max(0.0, spread_value or 0.0) + max(0.0, slippage or 0.0)
    if spread_value is None and slippage is None:
        return None
    return _clamp(1.0 - total / max(expected_move, 1.0))


def _score_cost_pressure(
    expected_move: float,
    total_cost: float,
    fees: float | None,
    spread: float | None,
    slippage: float | None,
    latency: float | None,
) -> float:
    explicit_parts = [value for value in (fees, spread, slippage, latency) if value is not None]
    cost = sum(max(0.0, value) for value in explicit_parts) if explicit_parts else max(0.0, total_cost)
    return _clamp(1.0 - cost / max(expected_move, 1.0))


def _score_health(source: Mapping[str, Any], prefix: str) -> float | None:
    explicit = _score_alias(source, (f"{prefix}_health_score", f"{prefix}_health"))
    if explicit is not None:
        return explicit
    penalty = _first_float(source, (f"{prefix}_health_penalty_bps", f"{prefix}_penalty_bps"))
    if penalty is None:
        return None
    return _clamp(1.0 - max(0.0, penalty) / 100.0)


def _score_alias(source: Mapping[str, Any], aliases: Sequence[str]) -> float | None:
    value = _first_float(source, aliases)
    if value is None:
        return None
    if 0.0 <= value <= 1.0:
        return value
    if 1.0 < value <= 100.0:
        return _clamp(value / 100.0)
    return _clamp(value)


def _first_float(source: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = _deep_get(source, key)
        parsed = _optional_float(value)
        if parsed is not None:
            return parsed
    return None


def _deep_get(source: Any, key: str) -> Any:
    if isinstance(source, Mapping):
        if key in source:
            return source[key]
        for value in source.values():
            found = _deep_get(value, key)
            if found is not None:
                return found
    elif isinstance(source, (list, tuple)):
        for item in source:
            found = _deep_get(item, key)
            if found is not None:
                return found
    return None


def _audit_no_lookahead(source: Mapping[str, Any]) -> None:
    paths = _forbidden_paths(source)
    if paths:
        raise LookaheadInputError(f"opportunity_score_v2 input contains post-entry fields: {', '.join(paths)}")


def _forbidden_paths(source: Any, prefix: str = "") -> tuple[str, ...]:
    paths: list[str] = []
    if isinstance(source, Mapping):
        for key, value in source.items():
            normalized = str(key).lower()
            path = f"{prefix}.{key}" if prefix else str(key)
            if normalized in FORBIDDEN_SCORE_V2_KEYS or normalized in FORBIDDEN_SCORE_V2_CONTAINER_KEYS:
                paths.append(path)
                continue
            paths.extend(_forbidden_paths(value, path))
    elif isinstance(source, (list, tuple)):
        for index, value in enumerate(source):
            paths.extend(_forbidden_paths(value, f"{prefix}[{index}]"))
    return tuple(paths)


def _reason(score: float | None, missing: Sequence[str], estimated_net_edge: float) -> str:
    if score is None:
        return "missing_required_pretrade_components"
    if estimated_net_edge <= 0.0:
        return "non_positive_forward_net_edge"
    if missing:
        return "partial_pretrade_components"
    if score >= HIGH_THRESHOLD:
        return "strong_pretrade_asymmetry"
    if score >= MEDIUM_THRESHOLD:
        return "moderate_pretrade_asymmetry"
    return "weak_pretrade_asymmetry"


def _empty_components() -> dict[str, float | None]:
    return {name: None for name in COMPONENT_WEIGHTS}


def _safe_float(source: Mapping[str, Any], key: str) -> float:
    return _optional_float(_deep_get(source, key)) or 0.0


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))
