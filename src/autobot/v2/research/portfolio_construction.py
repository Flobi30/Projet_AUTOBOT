"""Research-only portfolio construction and capacity checks.

This module turns versioned :class:`AlphaSignal` values into one immutable
``TargetPortfolio``.  It has no order-router, broker or paper-engine imports:
the result remains a non-executable research/shadow decision that an
independent risk layer must review later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    # Volume is retained as diagnostics, but it is not interchangeable with
    # immediately executable depth and therefore cannot authorize capacity.
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
class CapacityObservation:
    """Point-in-time liquidity evidence used only for a research review."""

    symbol: str
    observed_liquidity_eur: float | None = None
    observed_volume_eur: float | None = None
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        # Reuse the validation rules without inventing a trading notional.
        CapacityInput(
            symbol=self.symbol,
            desired_notional_eur=1.0,
            observed_liquidity_eur=self.observed_liquidity_eur,
            observed_volume_eur=self.observed_volume_eur,
            observed_at=self.observed_at,
        )


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


@dataclass(frozen=True)
class CapacityCurvePoint:
    """One conservative capacity observation at a proposed capital level."""

    desired_notional_eur: float
    maximum_capacity_eur: float | None
    utilization_ratio: float | None
    status: str
    reason: str


@dataclass(frozen=True)
class CapacityCurve:
    """Deterministic research-only capacity curve from observed liquidity."""

    symbol: str
    observed_capacity_source: str | None
    observed_liquidity_eur: float | None
    participation_limit: float
    points: tuple[CapacityCurvePoint, ...]
    status: str
    reason: str
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False


@dataclass(frozen=True)
class PortfolioCapacityReview:
    """Fail-closed capacity evidence for an entire research target portfolio.

    This review only translates target weights into proposed notionals and
    checks them against observed, point-in-time liquidity. It cannot create an
    order, alter allocation, or authorize paper/live execution.
    """

    decision_id: str
    decision_at: datetime
    capital_eur: float
    target_notionals_eur: Mapping[str, float]
    estimates: tuple[CapacityEstimate, ...]
    status: str
    reasons: tuple[str, ...]
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        if self.decision_at.tzinfo is None or self.decision_at.utcoffset() is None:
            raise PortfolioConstructionError("decision_at must be timezone-aware")
        if not math.isfinite(float(self.capital_eur)) or float(self.capital_eur) <= 0.0:
            raise PortfolioConstructionError("capital_eur must be positive and finite")
        object.__setattr__(self, "decision_at", self.decision_at.astimezone(timezone.utc))
        object.__setattr__(
            self,
            "target_notionals_eur",
            {str(symbol).upper(): float(notional) for symbol, notional in sorted(self.target_notionals_eur.items())},
        )


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
    data_snapshot_ids: set[str] = set()
    feature_versions: dict[str, str] = {}
    accepted: list[str] = []
    rejected: list[SignalRejection] = []

    for signal in sorted(signals, key=lambda item: item.signal_id):
        reason = _signal_rejection_reason(signal, decision_at=decision_at, cash_asset=cash_asset, config=config)
        if reason is not None:
            rejected.append(SignalRejection(signal.signal_id, reason))
            continue
        conflicting_feature = next(
            (
                feature_id
                for feature_id, version in signal.feature_versions.items()
                if feature_id in feature_versions and feature_versions[feature_id] != version
            ),
            None,
        )
        if conflicting_feature is not None:
            rejected.append(SignalRejection(signal.signal_id, f"feature_version_conflict:{conflicting_feature}"))
            continue
        expected_edge = float(signal.expected_edge_bps or 0.0)
        symbol = signal.market.symbol.upper()
        scores[symbol] = scores.get(symbol, 0.0) + expected_edge
        strategy_ids.setdefault(symbol, set()).add(signal.strategy_id)
        data_snapshot_ids.add(signal.data_snapshot_id)
        feature_versions.update(signal.feature_versions)
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
        cash_asset=cash_asset,
        source_signal_ids=tuple(accepted),
        source_strategy_ids=tuple(sorted({strategy_id for values in strategy_ids.values() for strategy_id in values})),
        source_data_snapshot_ids=tuple(sorted(data_snapshot_ids)),
        source_feature_versions=dict(sorted(feature_versions.items())),
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
    """Estimate whether a notional fits observed executable liquidity.

    Historical traded volume is not a substitute for point-in-time order-book
    depth.  It remains useful to describe market activity, but it cannot turn
    an otherwise unknown capacity into a tradable conclusion.
    """

    participation = float(max_liquidity_participation)
    if not math.isfinite(participation) or not 0.0 < participation <= 1.0:
        raise PortfolioConstructionError("max_liquidity_participation must be in (0, 1]")
    observed = request.observed_liquidity_eur
    if observed is None or observed <= 0.0:
        reason = (
            "observed_liquidity_missing_volume_not_executable_depth"
            if request.observed_volume_eur is not None
            else "observed_liquidity_missing"
        )
        return CapacityEstimate(
            symbol=request.symbol.upper(),
            desired_notional_eur=float(request.desired_notional_eur),
            observed_liquidity_eur=None,
            participation_limit=participation,
            maximum_capacity_eur=None,
            status="WAITING_FOR_MORE_DATA",
            reason=reason,
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


def estimate_capacity_curve(
    request: CapacityInput,
    *,
    desired_notionals_eur: Sequence[float],
    max_liquidity_participation: float,
) -> CapacityCurve:
    """Evaluate a bounded capital grid against the same observed capacity.

    This deliberately produces ``WAITING_FOR_MORE_DATA`` instead of estimating
    market depth from historical traded volume.  The curve is research-only
    evidence; callers must not use it to size an order.
    """

    notionals = tuple(sorted({float(value) for value in desired_notionals_eur}))
    if not notionals:
        raise PortfolioConstructionError("desired_notionals_eur must not be empty")
    if any(not math.isfinite(value) or value <= 0.0 for value in notionals):
        raise PortfolioConstructionError("desired_notionals_eur must be positive and finite")

    source = "observed_liquidity_eur" if request.observed_liquidity_eur is not None else None
    points: list[CapacityCurvePoint] = []
    for notional in notionals:
        estimate = estimate_capacity(
            CapacityInput(
                symbol=request.symbol,
                desired_notional_eur=notional,
                observed_liquidity_eur=request.observed_liquidity_eur,
                observed_volume_eur=request.observed_volume_eur,
                observed_at=request.observed_at,
            ),
            max_liquidity_participation=max_liquidity_participation,
        )
        maximum = estimate.maximum_capacity_eur
        points.append(
            CapacityCurvePoint(
                desired_notional_eur=notional,
                maximum_capacity_eur=maximum,
                utilization_ratio=(notional / maximum) if maximum and maximum > 0.0 else None,
                status=estimate.status,
                reason=estimate.reason,
            )
        )

    if source is None:
        status = "WAITING_FOR_MORE_DATA"
        reason = (
            "observed_liquidity_missing_volume_not_executable_depth"
            if request.observed_volume_eur is not None
            else "observed_liquidity_missing"
        )
    elif any(point.status == "CAPACITY_EXCEEDED" for point in points):
        status = "CAPACITY_EXCEEDED"
        reason = "one_or_more_capital_levels_exceed_observed_participation_limit"
    else:
        status = "CAPACITY_OK"
        reason = "all_capital_levels_within_observed_participation_limit"
    return CapacityCurve(
        symbol=request.symbol.upper(),
        observed_capacity_source=source,
        observed_liquidity_eur=float(request.observed_liquidity_eur) if request.observed_liquidity_eur is not None else None,
        participation_limit=float(max_liquidity_participation),
        points=tuple(points),
        status=status,
        reason=reason,
    )


def review_target_portfolio_capacity(
    target: TargetPortfolio,
    *,
    capital_eur: float,
    observations: Mapping[str, CapacityObservation],
    max_liquidity_participation: float,
    max_observation_age: timedelta = timedelta(minutes=2),
) -> PortfolioCapacityReview:
    """Review all target weights against fresh point-in-time capacity evidence.

    Missing, future-dated or stale observations are never replaced with a
    guessed depth. The resulting ``WAITING_FOR_MORE_DATA`` status prevents an
    optimistic capacity conclusion while preserving a clear audit trail.
    """

    capital = float(capital_eur)
    if not math.isfinite(capital) or capital <= 0.0:
        raise PortfolioConstructionError("capital_eur must be positive and finite")
    if max_observation_age <= timedelta(0):
        raise PortfolioConstructionError("max_observation_age must be positive")
    # Validate the shared participation setting even for an empty target.
    if not math.isfinite(float(max_liquidity_participation)) or not 0.0 < float(max_liquidity_participation) <= 1.0:
        raise PortfolioConstructionError("max_liquidity_participation must be in (0, 1]")

    decision_at = target.generated_at.astimezone(timezone.utc)
    normalized_observations = {str(symbol).upper(): observation for symbol, observation in observations.items()}
    target_notionals = {
        symbol.upper(): capital * float(weight)
        for symbol, weight in target.target_weights.items()
        if float(weight) > 0.0
    }
    if not target_notionals:
        return PortfolioCapacityReview(
            decision_id=target.decision_id,
            decision_at=decision_at,
            capital_eur=capital,
            target_notionals_eur={},
            estimates=(),
            status="NO_TARGET_EXPOSURE",
            reasons=("target_contains_no_investable_weight",),
        )

    estimates: list[CapacityEstimate] = []
    reasons: list[str] = []
    for symbol, desired_notional in sorted(target_notionals.items()):
        observation = normalized_observations.get(symbol)
        if observation is None:
            estimates.append(
                CapacityEstimate(
                    symbol=symbol,
                    desired_notional_eur=desired_notional,
                    observed_liquidity_eur=None,
                    participation_limit=float(max_liquidity_participation),
                    maximum_capacity_eur=None,
                    status="WAITING_FOR_MORE_DATA",
                    reason="capacity_observation_missing",
                )
            )
            reasons.append(f"{symbol}:capacity_observation_missing")
            continue
        if observation.symbol.upper() != symbol:
            raise PortfolioConstructionError("capacity observation symbol must match its mapping key")
        observed_at = observation.observed_at
        if observed_at is None:
            estimates.append(
                CapacityEstimate(
                    symbol=symbol,
                    desired_notional_eur=desired_notional,
                    observed_liquidity_eur=observation.observed_liquidity_eur,
                    participation_limit=float(max_liquidity_participation),
                    maximum_capacity_eur=None,
                    status="WAITING_FOR_MORE_DATA",
                    reason="capacity_observation_timestamp_missing",
                )
            )
            reasons.append(f"{symbol}:capacity_observation_timestamp_missing")
            continue
        observed_at = observed_at.astimezone(timezone.utc)
        if observed_at > decision_at:
            estimates.append(
                CapacityEstimate(
                    symbol=symbol,
                    desired_notional_eur=desired_notional,
                    observed_liquidity_eur=observation.observed_liquidity_eur,
                    participation_limit=float(max_liquidity_participation),
                    maximum_capacity_eur=None,
                    status="WAITING_FOR_MORE_DATA",
                    reason="capacity_observation_after_decision",
                )
            )
            reasons.append(f"{symbol}:capacity_observation_after_decision")
            continue
        if decision_at - observed_at > max_observation_age:
            estimates.append(
                CapacityEstimate(
                    symbol=symbol,
                    desired_notional_eur=desired_notional,
                    observed_liquidity_eur=observation.observed_liquidity_eur,
                    participation_limit=float(max_liquidity_participation),
                    maximum_capacity_eur=None,
                    status="WAITING_FOR_MORE_DATA",
                    reason="capacity_observation_stale",
                )
            )
            reasons.append(f"{symbol}:capacity_observation_stale")
            continue
        estimate = estimate_capacity(
            CapacityInput(
                symbol=symbol,
                desired_notional_eur=desired_notional,
                observed_liquidity_eur=observation.observed_liquidity_eur,
                observed_volume_eur=observation.observed_volume_eur,
                observed_at=observed_at,
            ),
            max_liquidity_participation=max_liquidity_participation,
        )
        estimates.append(estimate)
        if estimate.status != "CAPACITY_OK":
            reasons.append(f"{symbol}:{estimate.reason}")

    if any(item.status == "CAPACITY_EXCEEDED" for item in estimates):
        status = "CAPACITY_EXCEEDED"
    elif any(item.status != "CAPACITY_OK" for item in estimates):
        status = "WAITING_FOR_MORE_DATA"
    else:
        status = "CAPACITY_OK"
    return PortfolioCapacityReview(
        decision_id=target.decision_id,
        decision_at=decision_at,
        capital_eur=capital,
        target_notionals_eur=target_notionals,
        estimates=tuple(estimates),
        status=status,
        reasons=tuple(reasons) or ("all_target_notionals_within_observed_participation_limit",),
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
