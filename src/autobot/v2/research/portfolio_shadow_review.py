"""Research-only multi-signal portfolio review for the shadow boundary.

This module deliberately stops before ``OrderIntent``.  It proves that every
*accepted* component of one ``TargetPortfolio`` survives the shared pessimistic
cost gate and that every resulting exposure has fresh, market-bound capacity
evidence.  The result is an immutable research/shadow review, never an order
or a paper-capital authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

from autobot.v2.contracts import AlphaSignal

from .execution_cost_model import ExecutionCostConfig
from .execution_simulator import ScenarioEdgeReview, review_net_edge_scenarios
from .microstructure_cost_evidence import MicrostructureCostEvidence
from .portfolio_construction import (
    CapacityObservation,
    PortfolioCapacityReview,
    PortfolioConstructionConfig,
    PortfolioConstructionResult,
    build_target_portfolio,
    review_target_portfolio_capacity,
)


class PortfolioShadowReviewError(ValueError):
    """Raised when a multi-signal research review lacks a safe contract."""


@dataclass(frozen=True)
class PortfolioShadowReview:
    """Fail-closed review of one multi-signal research target portfolio.

    ``PORTFOLIO_SHADOW_READY`` means only that the target is internally
    coherent, each accepted component has survived the pessimistic cost review,
    and observed capacity covers every target exposure.  It is still not an
    approval to create an intent, to simulate a fill, or to use paper/live
    capital.
    """

    status: str
    reason: str
    decision_id: str
    decision_at: datetime
    input_signal_ids: tuple[str, ...]
    accepted_signal_ids: tuple[str, ...]
    target_result: PortfolioConstructionResult | None = None
    scenario_reviews: tuple[ScenarioEdgeReview, ...] = ()
    capacity_review: PortfolioCapacityReview | None = None
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        allowed_statuses = {
            "TARGET_REJECTED",
            "SCENARIO_BLOCKED",
            "CAPACITY_BLOCKED",
            "PORTFOLIO_SHADOW_READY",
        }
        status = str(self.status).strip().upper()
        if status not in allowed_statuses:
            raise PortfolioShadowReviewError("unsupported portfolio shadow review status")
        decision_id = str(self.decision_id).strip()
        if not decision_id:
            raise PortfolioShadowReviewError("decision_id is required")
        if self.decision_at.tzinfo is None or self.decision_at.utcoffset() is None:
            raise PortfolioShadowReviewError("decision_at must be timezone-aware")
        reason = str(self.reason).strip()
        if not reason:
            raise PortfolioShadowReviewError("reason is required")
        input_signal_ids = tuple(str(item).strip() for item in self.input_signal_ids)
        accepted_signal_ids = tuple(str(item).strip() for item in self.accepted_signal_ids)
        if not input_signal_ids or not all(input_signal_ids) or len(input_signal_ids) != len(set(input_signal_ids)):
            raise PortfolioShadowReviewError("input_signal_ids must be non-empty and unique")
        if not all(accepted_signal_ids) or len(accepted_signal_ids) != len(set(accepted_signal_ids)):
            raise PortfolioShadowReviewError("accepted_signal_ids must be unique")
        if not set(accepted_signal_ids).issubset(set(input_signal_ids)):
            raise PortfolioShadowReviewError("accepted_signal_ids must come from input_signal_ids")
        scenario_reviews = tuple(self.scenario_reviews)
        if any(not isinstance(item, ScenarioEdgeReview) for item in scenario_reviews):
            raise PortfolioShadowReviewError("scenario_reviews must contain ScenarioEdgeReview values")
        if tuple(item.signal_id for item in scenario_reviews) != tuple(sorted(item.signal_id for item in scenario_reviews)):
            raise PortfolioShadowReviewError("scenario_reviews must be ordered by signal_id")
        if {item.signal_id for item in scenario_reviews} - set(accepted_signal_ids):
            raise PortfolioShadowReviewError("scenario review exists for a rejected signal")
        if self.target_result is not None and not isinstance(self.target_result, PortfolioConstructionResult):
            raise PortfolioShadowReviewError("target_result must be a PortfolioConstructionResult")
        if self.capacity_review is not None and not isinstance(self.capacity_review, PortfolioCapacityReview):
            raise PortfolioShadowReviewError("capacity_review must be a PortfolioCapacityReview")
        if self.paper_capital_allowed or self.live_allowed or not self.research_only:
            raise PortfolioShadowReviewError("portfolio shadow review is research-only")
        if status == "PORTFOLIO_SHADOW_READY":
            if self.target_result is None or self.capacity_review is None:
                raise PortfolioShadowReviewError("ready portfolio shadow review requires target and capacity evidence")
            if self.capacity_review.status != "CAPACITY_OK":
                raise PortfolioShadowReviewError("ready portfolio shadow review requires capacity ok")
            if not scenario_reviews or any(
                item.status != "SCENARIO_EDGE_OK" or not item.pessimistic_passed for item in scenario_reviews
            ):
                raise PortfolioShadowReviewError("ready portfolio shadow review requires pessimistic cost survival")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "decision_id", decision_id)
        object.__setattr__(self, "decision_at", self.decision_at.astimezone(timezone.utc))
        object.__setattr__(self, "input_signal_ids", tuple(sorted(input_signal_ids)))
        object.__setattr__(self, "accepted_signal_ids", tuple(sorted(accepted_signal_ids)))
        object.__setattr__(self, "scenario_reviews", scenario_reviews)


def review_portfolio_in_shadow(
    signals: Sequence[AlphaSignal],
    *,
    decision_id: str,
    decision_at: datetime,
    capital_eur: float,
    capacity_observations: Mapping[str, CapacityObservation],
    max_liquidity_participation: float,
    base_cost_config: ExecutionCostConfig,
    portfolio_config: PortfolioConstructionConfig = PortfolioConstructionConfig(),
    microstructure_cost_evidence_by_symbol: Mapping[str, MicrostructureCostEvidence] | None = None,
) -> PortfolioShadowReview:
    """Review a complete research target before any order-oriented boundary.

    Invalid input signals are retained as auditable target rejections, rather
    than contaminating the scenario review for valid signals.  Every accepted
    target component must pass the pessimistic shared-cost scenario and every
    resulting target market must have its own point-in-time capacity evidence.
    """

    if decision_at.tzinfo is None or decision_at.utcoffset() is None:
        raise PortfolioShadowReviewError("decision_at must be timezone-aware")
    normalized_decision_at = decision_at.astimezone(timezone.utc)
    input_signals = tuple(signals)
    if not input_signals:
        raise PortfolioShadowReviewError("at least one AlphaSignal is required")
    if any(not isinstance(signal, AlphaSignal) for signal in input_signals):
        raise PortfolioShadowReviewError("signals must contain AlphaSignal values")
    input_signal_ids = tuple(signal.signal_id for signal in input_signals)
    if len(input_signal_ids) != len(set(input_signal_ids)):
        raise PortfolioShadowReviewError("signals must have unique signal_id values")

    evidence_by_symbol = _normalize_evidence_by_symbol(microstructure_cost_evidence_by_symbol)
    target_result = build_target_portfolio(
        input_signals,
        decision_id=decision_id,
        decision_at=normalized_decision_at,
        config=portfolio_config,
    )
    accepted_signal_ids = target_result.accepted_signal_ids
    if not accepted_signal_ids or not target_result.target.target_weights:
        reason = (
            target_result.rejected_signals[0].reason
            if target_result.rejected_signals
            else "target_contains_no_investable_weight"
        )
        return PortfolioShadowReview(
            "TARGET_REJECTED",
            reason,
            decision_id,
            normalized_decision_at,
            input_signal_ids,
            accepted_signal_ids,
            target_result=target_result,
        )

    signal_by_id = {signal.signal_id: signal for signal in input_signals}
    scenario_reviews = tuple(
        review_net_edge_scenarios(
            signal_by_id[signal_id],
            base_cost_config=base_cost_config,
            microstructure_cost_evidence=evidence_by_symbol.get(signal_by_id[signal_id].market.symbol),
        )
        for signal_id in sorted(accepted_signal_ids)
    )
    blocked_scenario = next(
        (
            review
            for review in scenario_reviews
            if review.status != "SCENARIO_EDGE_OK" or not review.pessimistic_passed
        ),
        None,
    )
    if blocked_scenario is not None:
        return PortfolioShadowReview(
            "SCENARIO_BLOCKED",
            f"{blocked_scenario.signal_id}:{blocked_scenario.reason}",
            decision_id,
            normalized_decision_at,
            input_signal_ids,
            accepted_signal_ids,
            target_result=target_result,
            scenario_reviews=scenario_reviews,
        )

    capacity_review = review_target_portfolio_capacity(
        target_result.target,
        capital_eur=capital_eur,
        observations=capacity_observations,
        expected_markets=target_result.target.source_markets,
        max_liquidity_participation=max_liquidity_participation,
    )
    if capacity_review.status != "CAPACITY_OK":
        return PortfolioShadowReview(
            "CAPACITY_BLOCKED",
            capacity_review.status.lower(),
            decision_id,
            normalized_decision_at,
            input_signal_ids,
            accepted_signal_ids,
            target_result=target_result,
            scenario_reviews=scenario_reviews,
            capacity_review=capacity_review,
        )

    return PortfolioShadowReview(
        "PORTFOLIO_SHADOW_READY",
        "all_target_components_survive_pessimistic_cost_and_capacity_review",
        decision_id,
        normalized_decision_at,
        input_signal_ids,
        accepted_signal_ids,
        target_result=target_result,
        scenario_reviews=scenario_reviews,
        capacity_review=capacity_review,
    )


def _normalize_evidence_by_symbol(
    values: Mapping[str, MicrostructureCostEvidence] | None,
) -> Mapping[str, MicrostructureCostEvidence]:
    normalized: dict[str, MicrostructureCostEvidence] = {}
    for raw_symbol, evidence in (values or {}).items():
        symbol = str(raw_symbol).strip().upper()
        if not symbol or not isinstance(evidence, MicrostructureCostEvidence):
            raise PortfolioShadowReviewError("microstructure evidence must use non-empty symbol keys")
        if symbol != evidence.market.symbol:
            raise PortfolioShadowReviewError("microstructure evidence symbol must match its MarketIdentity")
        if symbol in normalized:
            raise PortfolioShadowReviewError("microstructure evidence symbols must be unique case-insensitively")
        normalized[symbol] = evidence
    return normalized
