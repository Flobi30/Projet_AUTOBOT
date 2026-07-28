"""Research-only bridge from a target portfolio to a proposed shadow notional.

This module derives a deterministic :class:`SizingDecision` from immutable
portfolio, capacity and mandate facts.  It has no execution imports and cannot
create an intent, fill or command.
"""

from __future__ import annotations

from datetime import datetime
import math

from autobot.v2.contracts import (
    MarketIdentity,
    SizingDecision,
    StrategyArtifactReference,
    TargetPortfolio,
    contract_fingerprint,
)

from .portfolio_construction import PortfolioCapacityReview


class ResearchSizingError(ValueError):
    """Raised when a caller cannot supply the immutable sizing inputs."""


def derive_research_sizing_decision(
    *,
    target: TargetPortfolio,
    capacity_review: PortfolioCapacityReview,
    strategy_artifact: StrategyArtifactReference,
    market: MarketIdentity,
) -> SizingDecision:
    """Derive one bounded, non-executable notional for a shadow review.

    A target cannot select a capital amount itself. The proposed notional must
    exactly equal the independently reviewed capacity amount and remain below
    the immutable shadow mandate limit.
    """

    if not isinstance(target, TargetPortfolio):
        raise ResearchSizingError("target_portfolio_required")
    if not isinstance(capacity_review, PortfolioCapacityReview):
        raise ResearchSizingError("capacity_review_required")
    if not isinstance(strategy_artifact, StrategyArtifactReference):
        raise ResearchSizingError("strategy_artifact_required")
    if not isinstance(market, MarketIdentity):
        raise ResearchSizingError("market_identity_required")

    mandate_fingerprint = (
        strategy_artifact.risk_mandate.fingerprint
        if strategy_artifact.risk_mandate is not None
        else "risk_mandate_missing"
    )
    common = {
        "decision_id": target.decision_id,
        "generated_at": capacity_review.decision_at,
        "market": market,
        "target_portfolio_fingerprint": contract_fingerprint(target),
        "capacity_review_fingerprint": contract_fingerprint(capacity_review),
        "risk_mandate_fingerprint": mandate_fingerprint,
        "target_weight": target.target_weights.get(market.symbol, 0.0),
        "reference_capital_eur": capacity_review.capital_eur,
    }
    reason = _binding_blocker(
        target=target,
        capacity_review=capacity_review,
        strategy_artifact=strategy_artifact,
        market=market,
    )
    if reason is not None:
        return SizingDecision(
            **common,
            proposed_notional_eur=0.0,
            status="REJECTED",
            reasons=(reason,),
        )
    target_weight = float(target.target_weights.get(market.symbol, 0.0))
    if target_weight <= 0.0:
        return SizingDecision(
            **common,
            proposed_notional_eur=0.0,
            status="NO_ALLOCATION",
            reasons=("target_weight_is_zero",),
        )
    if capacity_review.status != "CAPACITY_OK":
        return SizingDecision(
            **common,
            proposed_notional_eur=0.0,
            status="REJECTED",
            reasons=(f"capacity_review_{str(capacity_review.status).lower()}",),
        )
    proposed_notional = float(capacity_review.target_notionals_eur.get(market.symbol, 0.0))
    expected_notional = target_weight * float(capacity_review.capital_eur)
    if (
        not math.isfinite(proposed_notional)
        or proposed_notional <= 0.0
        or not math.isclose(proposed_notional, expected_notional, rel_tol=0.0, abs_tol=1e-9)
    ):
        return SizingDecision(
            **common,
            proposed_notional_eur=0.0,
            status="REJECTED",
            reasons=("capacity_notional_mismatch",),
        )
    mandate = strategy_artifact.risk_mandate
    if mandate is None:
        return SizingDecision(
            **common,
            proposed_notional_eur=0.0,
            status="REJECTED",
            reasons=("risk_mandate_missing",),
        )
    if not mandate.is_current(capacity_review.decision_at):
        return SizingDecision(
            **common,
            proposed_notional_eur=0.0,
            status="REJECTED",
            reasons=("risk_mandate_expired",),
        )
    if proposed_notional > mandate.shadow_notional_max_eur + 1e-12:
        return SizingDecision(
            **common,
            proposed_notional_eur=0.0,
            status="REJECTED",
            reasons=("shadow_notional_limit_exceeded",),
        )
    return SizingDecision(
        **common,
        proposed_notional_eur=proposed_notional,
        status="READY_FOR_SHADOW_REVIEW",
        reasons=("research_only_not_executable",),
    )


def research_sizing_blocker(
    sizing: SizingDecision | None,
    *,
    target: TargetPortfolio,
    capacity_review: PortfolioCapacityReview,
    strategy_artifact: StrategyArtifactReference,
    market: MarketIdentity,
) -> str | None:
    """Validate that a supplied sizing decision is bound to exact inputs."""

    if not isinstance(sizing, SizingDecision):
        return "sizing_decision_required"
    mandate = strategy_artifact.risk_mandate
    expected = {
        "decision_id": target.decision_id,
        "market": market,
        "target_portfolio_fingerprint": contract_fingerprint(target),
        "capacity_review_fingerprint": contract_fingerprint(capacity_review),
        "risk_mandate_fingerprint": mandate.fingerprint if mandate is not None else "risk_mandate_missing",
    }
    for field_name, value in expected.items():
        if getattr(sizing, field_name) != value:
            return f"sizing_decision_{field_name}_mismatch"
    if sizing.status != "READY_FOR_SHADOW_REVIEW":
        return f"sizing_decision_not_ready:{sizing.status.lower()}"
    if sizing.generated_at != capacity_review.decision_at:
        return "sizing_decision_time_mismatch"
    if not math.isclose(sizing.reference_capital_eur, capacity_review.capital_eur, rel_tol=0.0, abs_tol=1e-9):
        return "sizing_decision_reference_capital_mismatch"
    target_weight = float(target.target_weights.get(market.symbol, 0.0))
    if not math.isclose(sizing.target_weight, target_weight, rel_tol=0.0, abs_tol=1e-12):
        return "sizing_decision_target_weight_mismatch"
    expected_notional = float(capacity_review.target_notionals_eur.get(market.symbol, 0.0))
    if not math.isclose(sizing.proposed_notional_eur, expected_notional, rel_tol=0.0, abs_tol=1e-9):
        return "sizing_decision_notional_mismatch"
    if sizing.paper_capital_allowed or sizing.live_allowed or not sizing.research_only:
        return "sizing_decision_permissions_invalid"
    return None


def _binding_blocker(
    *,
    target: TargetPortfolio,
    capacity_review: PortfolioCapacityReview,
    strategy_artifact: StrategyArtifactReference,
    market: MarketIdentity,
) -> str | None:
    if target.decision_id != capacity_review.decision_id:
        return "capacity_review_decision_id_mismatch"
    if target.source_markets.get(market.symbol) != market:
        return "target_market_identity_mismatch"
    if strategy_artifact.strategy_id not in target.source_strategy_ids:
        return "strategy_artifact_strategy_mismatch"
    if strategy_artifact.data_snapshot_id not in target.source_data_snapshot_ids:
        return "strategy_artifact_data_snapshot_mismatch"
    if strategy_artifact.risk_mandate is None:
        return "risk_mandate_missing"
    return None
