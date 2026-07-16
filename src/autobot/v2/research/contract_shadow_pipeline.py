"""One fail-closed contract path for research-only shadow simulation.

The module exists to exercise the same boundary objects that a future runtime
will need, without importing a router, an executor, a paper engine, or any
runtime service.  It cannot emit an ``ExecutionCommand`` and always remains
shadow/research-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import math
from typing import Mapping, Sequence

from autobot.v2.contracts import AlphaSignal, OrderIntent, RiskDecision, StrategyArtifactReference, TargetPortfolio

from .execution_simulator import ResearchExecutionOutcome, ResearchExecutionSimulator, ShadowMarketSnapshot
from .portfolio_construction import (
    CapacityObservation,
    PortfolioCapacityReview,
    PortfolioConstructionConfig,
    PortfolioConstructionResult,
    build_target_portfolio,
    review_target_portfolio_capacity,
)


@dataclass(frozen=True)
class ContractShadowPipelineReview:
    """Auditable result of one contract-driven, non-executable shadow path."""

    status: str
    reason: str
    alpha_signal: AlphaSignal
    target_result: PortfolioConstructionResult | None = None
    capacity_review: PortfolioCapacityReview | None = None
    order_intent: OrderIntent | None = None
    risk_decision: RiskDecision | None = None
    outcome: ResearchExecutionOutcome | None = None
    execution_command_created: bool = False
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False


def evaluate_alpha_signal_in_shadow(
    signal: AlphaSignal,
    *,
    decision_id: str,
    strategy_artifact: StrategyArtifactReference,
    capital_eur: float,
    capacity_observations: Mapping[str, CapacityObservation],
    max_liquidity_participation: float,
    simulator: ResearchExecutionSimulator,
    snapshots: Sequence[ShadowMarketSnapshot],
    risk_decision: RiskDecision | None,
    portfolio_config: PortfolioConstructionConfig = PortfolioConstructionConfig(),
) -> ContractShadowPipelineReview:
    """Evaluate exactly one alpha through target, capacity, risk and shadow.

    The return value records the first blocking boundary.  No fallback creates
    an order from missing capacity, mismatched provenance or a denied risk
    decision.  Even the successful path ends at the isolated shadow simulator.
    """

    reason = _artifact_matches_signal(strategy_artifact, signal)
    if reason is not None:
        return ContractShadowPipelineReview("CONTRACT_REJECTED", reason, signal, risk_decision=risk_decision)
    if not math.isclose(
        float(max_liquidity_participation),
        float(simulator.cost_config.max_liquidity_participation),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        return ContractShadowPipelineReview(
            "CONTRACT_REJECTED",
            "capacity_participation_limit_mismatch",
            signal,
            risk_decision=risk_decision,
        )

    target_result = build_target_portfolio(
        (signal,),
        decision_id=decision_id,
        decision_at=signal.available_at,
        config=portfolio_config,
    )
    if signal.signal_id not in target_result.accepted_signal_ids:
        reason = target_result.rejected_signals[0].reason if target_result.rejected_signals else "target_portfolio_rejected"
        return ContractShadowPipelineReview(
            "TARGET_REJECTED",
            reason,
            signal,
            target_result=target_result,
            risk_decision=risk_decision,
        )

    capacity_review = review_target_portfolio_capacity(
        target_result.target,
        capital_eur=capital_eur,
        observations=capacity_observations,
        max_liquidity_participation=max_liquidity_participation,
    )
    if capacity_review.status != "CAPACITY_OK":
        return ContractShadowPipelineReview(
            "CAPACITY_BLOCKED",
            capacity_review.status.lower(),
            signal,
            target_result=target_result,
            capacity_review=capacity_review,
            risk_decision=risk_decision,
        )

    symbol = signal.market.symbol.upper()
    target_notional = float(capacity_review.target_notionals_eur.get(symbol, 0.0))
    if not math.isfinite(target_notional) or target_notional <= 0.0:
        return ContractShadowPipelineReview(
            "CONTRACT_REJECTED",
            "target_notional_missing_after_capacity_review",
            signal,
            target_result=target_result,
            capacity_review=capacity_review,
            risk_decision=risk_decision,
        )

    intent = OrderIntent(
        decision_id=decision_id,
        strategy_id=signal.strategy_id,
        strategy_artifact=strategy_artifact,
        market=signal.market,
        side="buy",
        target_notional=target_notional,
        created_at=signal.available_at,
        data_available_at=signal.available_at,
        execution_mode="shadow",
        client_order_id=_client_order_id(decision_id, signal, strategy_artifact),
        metadata={
            "source": "contract_shadow_pipeline/v1",
            "signal_id": signal.signal_id,
            "target_weight": target_result.target.target_weights[symbol],
            "capacity_status": capacity_review.status,
            "expected_edge_bps": signal.expected_edge_bps,
            "paper_capital_allowed": False,
            "live_allowed": False,
        },
    )
    outcome = simulator.simulate(intent, snapshots, risk_decision=risk_decision)
    return ContractShadowPipelineReview(
        f"SHADOW_{outcome.status}",
        outcome.reason,
        signal,
        target_result=target_result,
        capacity_review=capacity_review,
        order_intent=intent,
        risk_decision=risk_decision,
        outcome=outcome,
    )


def _artifact_matches_signal(artifact: StrategyArtifactReference, signal: AlphaSignal) -> str | None:
    if artifact.strategy_id != signal.strategy_id.lower():
        return "strategy_artifact_strategy_mismatch"
    if artifact.strategy_version != signal.strategy_version:
        return "strategy_artifact_version_mismatch"
    if artifact.data_snapshot_id != signal.data_snapshot_id:
        return "strategy_artifact_data_snapshot_mismatch"
    if dict(artifact.feature_versions) != dict(signal.feature_versions):
        return "strategy_artifact_feature_versions_mismatch"
    return None


def _client_order_id(decision_id: str, signal: AlphaSignal, artifact: StrategyArtifactReference) -> str:
    identity = "|".join((decision_id, signal.signal_id, artifact.artifact_id, signal.market.symbol))
    return f"research_shadow_{sha256(identity.encode('utf-8')).hexdigest()[:24]}"
