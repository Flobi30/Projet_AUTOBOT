"""Research-only portfolio construction and capacity checks.

This module turns versioned :class:`AlphaSignal` values into one immutable
``TargetPortfolio``.  It has no order-router, broker or paper-engine imports:
the result remains a non-executable research/shadow decision that an
independent risk layer must review later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Mapping, Sequence

from autobot.v2.contracts import AlphaSignal, TargetPortfolio


class PortfolioConstructionError(ValueError):
    """Raised when a research portfolio cannot be built safely."""


@dataclass(frozen=True)
class PortfolioConstructionConfig:
    """Long-only spot constraints for research and shadow construction."""

    cash_asset: str = "EUR"
    reserve_cash_weight: float = 0.20
    max_symbol_weight: float = 0.35
    min_expected_edge_bps: float = 0.0
    max_turnover_weight: float = 0.50
    allow_short: bool = False
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.cash_asset.strip():
            raise PortfolioConstructionError("cash_asset is required")
        for field_name in ("reserve_cash_weight", "max_symbol_weight", "max_turnover_weight"):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise PortfolioConstructionError(f"{field_name} must be in [0, 1]")
        if self.max_symbol_weight <= 0.0:
            raise PortfolioConstructionError("max_symbol_weight must be positive")
        if not math.isfinite(float(self.min_expected_edge_bps)):
            raise PortfolioConstructionError("min_expected_edge_bps must be finite")
        if self.allow_short or self.paper_capital_allowed or self.live_allowed or not self.research_only:
            raise PortfolioConstructionError("portfolio construction is research-only and spot long-only")


@dataclass(frozen=True)
class SignalRejection:
    signal_id: str
    reason: str


@dataclass(frozen=True)
class PortfolioConstructionResult:
    target: TargetPortfolio
    accepted_signal_ids: tuple[str, ...]
    rejected_signals: tuple[SignalRejection, ...]
    turnover_weight: float
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False


@dataclass(frozen=True)
class CapacityInput:
    symbol: str
    desired_notional_eur: float
    observed_liquidity_eur: float | None = None
    observed_volume_eur: float | None = None
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not str(self.symbol).strip():
            raise PortfolioConstructionError("capacity symbol is required")
        if not math.isfinite(float(self.desired_notional_eur)) or float(self.desired_notional_eur) <= 0.0:
            raise PortfolioConstructionError("desired_notional_eur must be positive and finite")
        for field_name in ("observed_liquidity_eur", "observed_volume_eur"):
            value = getattr(self, field_name)
            if value is not None and (not math.isfinite(float(value)) or float(value) < 0.0):
                raise PortfolioConstructionError(f"{field_name} must be non-negative and finite")
        if self.observed_at is not None and (self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None):
            raise PortfolioConstructionError("observed_at must be timezone-aware")


@dataclass(frozen=True)
class CapacityEstimate:
    symbol: str
    desired_notional_eur: float
    observed_liquidity_eur: float | None
    participation_limit: float
    maximum_capacity_eur: float | None
    status: str
    reason: str
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False


def build_target_portfolio(
    signals: Sequence[AlphaSignal],
    *,
    decision_id: str,
    decision_at: datetime,
    current_weights: Mapping[str, float] | None = None,
    config: PortfolioConstructionConfig = PortfolioConstructionConfig(),
) -> PortfolioConstructionResult:
    """Build a conservative target using only information available by ``decision_at``.

    A short signal, a non-spot market, an implicit quote conversion, an
    unavailable signal, or a non-positive expected edge produces an auditable
    rejection rather than an order.  The function is deterministic for a fixed
    set of signal contracts.
    """

    if decision_at.tzinfo is None or decision_at.utcoffset() is None:
        raise PortfolioConstructionError("decision_at must be timezone-aware")
    decision_at = decision_at.astimezone(timezone.utc)
    cash_asset = config.cash_asset.upper()
    scores: dict[str, float] = {}
    strategy_ids: dict[str, set[str]] = {}
    accepted: list[str] = []
    rejected: list[SignalRejection] = []

    for signal in sorted(signals, key=lambda item: item.signal_id):
        reason = _signal_rejection_reason(signal, decision_at=decision_at, cash_asset=cash_asset, config=config)
        if reason is not None:
            rejected.append(SignalRejection(signal.signal_id, reason))
            continue
        expected_edge = float(signal.expected_edge_bps or 0.0)
        symbol = signal.market.symbol.upper()
        scores[symbol] = scores.get(symbol, 0.0) + expected_edge
        strategy_ids.setdefault(symbol, set()).add(signal.strategy_id)
        accepted.append(signal.signal_id)

    target_weights = _capped_score_weights(scores, investable_weight=1.0 - config.reserve_cash_weight, cap=config.max_symbol_weight)
    target_weights, turnover = _apply_turnover_limit(
        target_weights,
        current_weights=current_weights or {},
        max_turnover_weight=config.max_turnover_weight,
    )
    reserve = max(0.0, 1.0 - sum(target_weights.values()))
    rationale = {
        symbol: (
            f"expected_edge_bps={scores[symbol]:.6f};"
            f"strategies={','.join(sorted(strategy_ids[symbol]))};"
            f"research_only"
            if symbol in scores
            else "legacy_exposure_retained_only_to_respect_turnover_limit;research_only"
        )
        for symbol in sorted(target_weights)
        if target_weights[symbol] > 0.0
    }
    target = TargetPortfolio(
        decision_id=decision_id,
        generated_at=decision_at,
        target_weights={symbol: weight for symbol, weight in sorted(target_weights.items()) if weight > 0.0},
        reserve_cash_weight=reserve,
        rationale=rationale,
    )
    return PortfolioConstructionResult(
        target=target,
        accepted_signal_ids=tuple(accepted),
        rejected_signals=tuple(rejected),
        turnover_weight=turnover,
    )


def estimate_capacity(
    request: CapacityInput,
    *,
    max_liquidity_participation: float,
) -> CapacityEstimate:
    """Estimate whether a notional fits observed liquidity without inventing depth."""

    participation = float(max_liquidity_participation)
    if not math.isfinite(participation) or not 0.0 < participation <= 1.0:
        raise PortfolioConstructionError("max_liquidity_participation must be in (0, 1]")
    observed = request.observed_liquidity_eur
    if observed is None:
        observed = request.observed_volume_eur
    if observed is None or observed <= 0.0:
        return CapacityEstimate(
            symbol=request.symbol.upper(),
            desired_notional_eur=float(request.desired_notional_eur),
            observed_liquidity_eur=None,
            participation_limit=participation,
            maximum_capacity_eur=None,
            status="WAITING_FOR_MORE_DATA",
            reason="observed_liquidity_missing",
        )
    maximum = float(observed) * participation
    status = "CAPACITY_OK" if float(request.desired_notional_eur) <= maximum else "CAPACITY_EXCEEDED"
    return CapacityEstimate(
        symbol=request.symbol.upper(),
        desired_notional_eur=float(request.desired_notional_eur),
        observed_liquidity_eur=float(observed),
        participation_limit=participation,
        maximum_capacity_eur=maximum,
        status=status,
        reason="within_observed_participation_limit" if status == "CAPACITY_OK" else "desired_notional_exceeds_observed_participation_limit",
    )


def _signal_rejection_reason(
    signal: AlphaSignal,
    *,
    decision_at: datetime,
    cash_asset: str,
    config: PortfolioConstructionConfig,
) -> str | None:
    if signal.available_at > decision_at:
        return "signal_not_yet_available"
    if signal.market.market_type != "spot":
        return "non_spot_market_not_allowed"
    if signal.market.quote_asset != cash_asset:
        return "implicit_quote_conversion_not_allowed"
    if signal.direction == "short" and not config.allow_short:
        return "short_not_allowed"
    if signal.direction != "long":
        return "flat_or_unsupported_direction"
    edge = signal.expected_edge_bps
    if edge is None:
        return "expected_edge_missing"
    if not math.isfinite(float(edge)) or float(edge) <= config.min_expected_edge_bps:
        return "expected_edge_below_threshold"
    return None


def _capped_score_weights(scores: Mapping[str, float], *, investable_weight: float, cap: float) -> dict[str, float]:
    eligible = {str(symbol).upper(): float(score) for symbol, score in scores.items() if float(score) > 0.0}
    if not eligible or investable_weight <= 0.0:
        return {}
    remaining = min(1.0, max(0.0, float(investable_weight)))
    capacity = {symbol: min(float(cap), remaining) for symbol in eligible}
    weights = {symbol: 0.0 for symbol in eligible}
    active = set(eligible)
    while active and remaining > 1e-12:
        score_total = sum(eligible[symbol] for symbol in active)
        if score_total <= 0.0:
            break
        allocated = 0.0
        next_active: set[str] = set()
        for symbol in sorted(active):
            requested = remaining * (eligible[symbol] / score_total)
            room = capacity[symbol] - weights[symbol]
            addition = min(requested, max(0.0, room))
            weights[symbol] += addition
            allocated += addition
            if capacity[symbol] - weights[symbol] > 1e-12:
                next_active.add(symbol)
        if allocated <= 1e-12:
            break
        remaining -= allocated
        active = next_active
    return {symbol: round(weight, 12) for symbol, weight in weights.items() if weight > 1e-12}


def _apply_turnover_limit(
    desired: Mapping[str, float],
    *,
    current_weights: Mapping[str, float],
    max_turnover_weight: float,
) -> tuple[dict[str, float], float]:
    current = {str(symbol).upper(): float(weight) for symbol, weight in current_weights.items() if float(weight) > 0.0}
    if any(not math.isfinite(weight) or weight < 0.0 for weight in current.values()) or sum(current.values()) > 1.000001:
        raise PortfolioConstructionError("current_weights must be finite, non-negative and sum to at most one")
    symbols = sorted(set(desired) | set(current))
    raw_turnover = 0.5 * sum(abs(float(desired.get(symbol, 0.0)) - float(current.get(symbol, 0.0))) for symbol in symbols)
    if raw_turnover <= max_turnover_weight + 1e-12 or raw_turnover <= 0.0:
        return dict(desired), raw_turnover
    ratio = max_turnover_weight / raw_turnover
    blended = {
        symbol: float(current.get(symbol, 0.0)) + ratio * (float(desired.get(symbol, 0.0)) - float(current.get(symbol, 0.0)))
        for symbol in symbols
    }
    return {symbol: round(weight, 12) for symbol, weight in blended.items() if weight > 1e-12}, max_turnover_weight
