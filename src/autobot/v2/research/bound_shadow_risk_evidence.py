"""Immutable pre-trade evidence for the isolated research shadow pipeline.

This module is deliberately detached from the runtime router, paper engine and
order executors.  It turns a side-effect-free ``PreTradeAutonomyGate`` review
into evidence that can be consumed by the contract shadow simulator, but it
cannot issue an execution command or grant paper/live permission.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math

from autobot.v2.contracts import (
    AlphaSignal,
    RiskDecision,
    SizingDecision,
    StrategyArtifactReference,
    TargetPortfolio,
    contract_fingerprint,
)

from .portfolio_construction import PortfolioCapacityReview
from .portfolio_sizing import research_sizing_blocker
from .strategy_risk_mandates import (
    DECISION_ALLOW,
    AutonomyDecision,
    PreTradeAutonomyGate,
    PreTradeAutonomyRequest,
    StrategyHealthSnapshot,
    StrategyRiskMandate,
)


class BoundShadowRiskEvidenceError(ValueError):
    """Raised when research-only pre-trade evidence is incomplete or inconsistent."""


@dataclass(frozen=True)
class BoundShadowRiskEvidence:
    """One immutable, non-authorizing mandate-gate review for a shadow target."""

    decision_id: str
    signal_id: str
    strategy_artifact_id: str
    strategy_artifact_fingerprint: str
    mandate_id: str
    mandate_fingerprint: str
    market_symbol: str
    target_portfolio_fingerprint: str
    capacity_review_fingerprint: str
    sizing_decision_fingerprint: str
    pre_trade_request: PreTradeAutonomyRequest
    health: StrategyHealthSnapshot
    gate_decision: str
    gate_reasons: tuple[str, ...]
    gate_checks_fingerprint: str
    risk_decision: RiskDecision
    evaluated_at: datetime
    target_notional_eur: float
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "decision_id",
            "signal_id",
            "strategy_artifact_id",
            "strategy_artifact_fingerprint",
            "mandate_id",
            "mandate_fingerprint",
            "market_symbol",
            "target_portfolio_fingerprint",
            "capacity_review_fingerprint",
            "sizing_decision_fingerprint",
            "gate_checks_fingerprint",
        ):
            if not str(getattr(self, field_name)).strip():
                raise BoundShadowRiskEvidenceError(f"{field_name} is required")
        if not isinstance(self.pre_trade_request, PreTradeAutonomyRequest):
            raise BoundShadowRiskEvidenceError("pre_trade_request is required")
        if not isinstance(self.health, StrategyHealthSnapshot):
            raise BoundShadowRiskEvidenceError("health is required")
        if not isinstance(self.risk_decision, RiskDecision):
            raise BoundShadowRiskEvidenceError("risk_decision is required")
        evaluated_at = _utc(self.evaluated_at, "evaluated_at")
        target_notional_eur = float(self.target_notional_eur)
        if not math.isfinite(target_notional_eur) or target_notional_eur <= 0.0:
            raise BoundShadowRiskEvidenceError("target_notional_eur must be positive and finite")
        if str(self.gate_decision).strip().upper() != DECISION_ALLOW:
            raise BoundShadowRiskEvidenceError("shadow risk evidence requires an ALLOW gate decision")
        gate_reasons = tuple(str(reason).strip() for reason in self.gate_reasons)
        if not gate_reasons or not all(gate_reasons):
            raise BoundShadowRiskEvidenceError("gate_reasons are required")
        if not self.risk_decision.approved:
            raise BoundShadowRiskEvidenceError("shadow risk evidence requires an approved risk decision")
        if self.risk_decision.decision_id != self.decision_id:
            raise BoundShadowRiskEvidenceError("risk decision_id must match evidence decision_id")
        if self.risk_decision.decided_at < evaluated_at:
            raise BoundShadowRiskEvidenceError("risk decision cannot precede its gate evaluation")
        if self.paper_capital_allowed or self.live_allowed or not self.research_only:
            raise BoundShadowRiskEvidenceError("bound shadow risk evidence is research-only")
        object.__setattr__(self, "decision_id", str(self.decision_id).strip())
        object.__setattr__(self, "signal_id", str(self.signal_id).strip())
        object.__setattr__(self, "strategy_artifact_id", str(self.strategy_artifact_id).strip())
        object.__setattr__(self, "strategy_artifact_fingerprint", str(self.strategy_artifact_fingerprint).strip())
        object.__setattr__(self, "mandate_id", str(self.mandate_id).strip())
        object.__setattr__(self, "mandate_fingerprint", str(self.mandate_fingerprint).strip())
        object.__setattr__(self, "market_symbol", str(self.market_symbol).strip().upper())
        object.__setattr__(self, "target_portfolio_fingerprint", str(self.target_portfolio_fingerprint).strip())
        object.__setattr__(self, "capacity_review_fingerprint", str(self.capacity_review_fingerprint).strip())
        object.__setattr__(self, "sizing_decision_fingerprint", str(self.sizing_decision_fingerprint).strip())
        object.__setattr__(self, "gate_decision", str(self.gate_decision).strip().upper())
        object.__setattr__(self, "gate_reasons", gate_reasons)
        object.__setattr__(self, "gate_checks_fingerprint", str(self.gate_checks_fingerprint).strip())
        object.__setattr__(self, "evaluated_at", evaluated_at)
        object.__setattr__(self, "target_notional_eur", target_notional_eur)

    @property
    def fingerprint(self) -> str:
        """Return a stable identity for this complete research review."""

        payload = {
            "decision_id": self.decision_id,
            "signal_id": self.signal_id,
            "strategy_artifact_id": self.strategy_artifact_id,
            "strategy_artifact_fingerprint": self.strategy_artifact_fingerprint,
            "mandate_id": self.mandate_id,
            "mandate_fingerprint": self.mandate_fingerprint,
            "market_symbol": self.market_symbol,
            "target_portfolio_fingerprint": self.target_portfolio_fingerprint,
            "capacity_review_fingerprint": self.capacity_review_fingerprint,
            "sizing_decision_fingerprint": self.sizing_decision_fingerprint,
            "pre_trade_request": _primitive(asdict(self.pre_trade_request)),
            "health": _primitive(asdict(self.health)),
            "gate_decision": self.gate_decision,
            "gate_reasons": self.gate_reasons,
            "gate_checks_fingerprint": self.gate_checks_fingerprint,
            "risk_decision": _primitive(asdict(self.risk_decision)),
            "evaluated_at": self.evaluated_at.isoformat(),
            "target_notional_eur": self.target_notional_eur,
            "research_only": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return sha256(encoded.encode("utf-8")).hexdigest()


def build_bound_shadow_risk_evidence(
    *,
    decision_id: str,
    signal: AlphaSignal,
    strategy_artifact: StrategyArtifactReference,
    target: TargetPortfolio,
    capacity_review: PortfolioCapacityReview,
    sizing_decision: SizingDecision,
    mandate: StrategyRiskMandate,
    pre_trade_request: PreTradeAutonomyRequest,
    health: StrategyHealthSnapshot | None = None,
    gate: PreTradeAutonomyGate | None = None,
) -> BoundShadowRiskEvidence:
    """Evaluate the mandate gate and bind its result to one shadow target.

    The function is pure and deterministic for the supplied inputs. It
    rejects a non-``ALLOW`` gate result. The contract pipeline
    only accepts an approved evidence object, so a blocked, killed or
    human-review decision cannot accidentally reach its simulator.
    """

    _validate_bindings(
        decision_id=decision_id,
        signal=signal,
        strategy_artifact=strategy_artifact,
        target=target,
        capacity_review=capacity_review,
        sizing_decision=sizing_decision,
        mandate=mandate,
        pre_trade_request=pre_trade_request,
    )
    health = health or StrategyHealthSnapshot()
    autonomy_decision = (gate or PreTradeAutonomyGate()).evaluate(mandate, pre_trade_request, health)
    if autonomy_decision.decision != DECISION_ALLOW:
        raise BoundShadowRiskEvidenceError(f"pre-trade autonomy gate did not allow shadow review: {autonomy_decision.decision}")
    if autonomy_decision.mandate_id != mandate.mandate_id:
        raise BoundShadowRiskEvidenceError("pre-trade autonomy gate mandate mismatch")
    if autonomy_decision.strategy_id.lower() != signal.strategy_id.lower():
        raise BoundShadowRiskEvidenceError("pre-trade autonomy gate strategy mismatch")
    if autonomy_decision.paper_capital_allowed or autonomy_decision.live_allowed or autonomy_decision.promotable:
        raise BoundShadowRiskEvidenceError("pre-trade autonomy gate returned an invalid execution permission")
    risk_decision = RiskDecision(
        decision_id=decision_id,
        approved=True,
        decided_at=pre_trade_request.evaluated_at or signal.available_at,
        reasons=("pretrade_autonomy_gate_allow",),
        warnings=("research_only_shadow_evidence",),
    )
    return BoundShadowRiskEvidence(
        decision_id=decision_id,
        signal_id=signal.signal_id,
        strategy_artifact_id=strategy_artifact.artifact_id,
        strategy_artifact_fingerprint=strategy_artifact.fingerprint,
        mandate_id=mandate.mandate_id,
        mandate_fingerprint=mandate.fingerprint,
        market_symbol=signal.market.symbol,
        target_portfolio_fingerprint=contract_fingerprint(target),
        capacity_review_fingerprint=contract_fingerprint(capacity_review),
        sizing_decision_fingerprint=contract_fingerprint(sizing_decision),
        pre_trade_request=pre_trade_request,
        health=health,
        gate_decision=autonomy_decision.decision,
        gate_reasons=autonomy_decision.reasons,
        gate_checks_fingerprint=_decision_fingerprint(autonomy_decision),
        risk_decision=risk_decision,
        evaluated_at=pre_trade_request.evaluated_at or signal.available_at,
        target_notional_eur=_target_notional(target, capacity_review, signal.market.symbol),
    )


def shadow_risk_evidence_blocker(
    evidence: BoundShadowRiskEvidence | None,
    *,
    decision_id: str,
    signal: AlphaSignal,
    strategy_artifact: StrategyArtifactReference,
    target: TargetPortfolio,
    capacity_review: PortfolioCapacityReview,
    sizing_decision: SizingDecision,
) -> str | None:
    """Return a fail-closed blocker if evidence cannot authorize a shadow review."""

    if evidence is None:
        return "bound_shadow_risk_evidence_missing"
    if not isinstance(evidence, BoundShadowRiskEvidence):
        return "bound_shadow_risk_evidence_invalid_type"
    mandate = strategy_artifact.risk_mandate
    if mandate is None:
        return "strategy_artifact_risk_mandate_missing"
    sizing_blocker = research_sizing_blocker(
        sizing_decision,
        target=target,
        capacity_review=capacity_review,
        strategy_artifact=strategy_artifact,
        market=signal.market,
    )
    if sizing_blocker is not None:
        return f"bound_shadow_risk_evidence_{sizing_blocker}"
    expected_notional = _target_notional(target, capacity_review, signal.market.symbol)
    expected = {
        "decision_id": decision_id,
        "signal_id": signal.signal_id,
        "strategy_artifact_id": strategy_artifact.artifact_id,
        "strategy_artifact_fingerprint": strategy_artifact.fingerprint,
        "mandate_id": mandate.mandate_id,
        "mandate_fingerprint": mandate.fingerprint,
        "market_symbol": signal.market.symbol.upper(),
        "target_portfolio_fingerprint": contract_fingerprint(target),
        "capacity_review_fingerprint": contract_fingerprint(capacity_review),
        "sizing_decision_fingerprint": contract_fingerprint(sizing_decision),
    }
    for field_name, value in expected.items():
        if getattr(evidence, field_name) != value:
            return f"bound_shadow_risk_evidence_{field_name}_mismatch"
    if evidence.pre_trade_request.strategy_id.lower() != signal.strategy_id.lower():
        return "bound_shadow_risk_evidence_strategy_mismatch"
    if evidence.pre_trade_request.symbol.upper() != signal.market.symbol:
        return "bound_shadow_risk_evidence_market_mismatch"
    if evidence.pre_trade_request.evaluated_at != signal.available_at:
        return "bound_shadow_risk_evidence_evaluation_time_mismatch"
    if not math.isclose(evidence.pre_trade_request.notional_eur, expected_notional, rel_tol=0.0, abs_tol=1e-12):
        return "bound_shadow_risk_evidence_notional_mismatch"
    if signal.expected_edge_bps is None or not math.isclose(
        evidence.pre_trade_request.estimated_edge_bps,
        float(signal.expected_edge_bps),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        return "bound_shadow_risk_evidence_expected_edge_mismatch"
    if evidence.gate_decision != DECISION_ALLOW:
        return "bound_shadow_risk_evidence_gate_not_allowed"
    if not evidence.risk_decision.approved:
        return "bound_shadow_risk_evidence_risk_not_approved"
    if evidence.risk_decision.decision_id != decision_id:
        return "bound_shadow_risk_evidence_risk_decision_mismatch"
    if evidence.risk_decision.decided_at < signal.available_at:
        return "bound_shadow_risk_evidence_risk_before_data_available"
    if evidence.risk_decision.reduced_notional is not None and evidence.risk_decision.reduced_notional > expected_notional + 1e-12:
        return "bound_shadow_risk_evidence_risk_increases_notional"
    if evidence.paper_capital_allowed or evidence.live_allowed or not evidence.research_only:
        return "bound_shadow_risk_evidence_permissions_invalid"
    return None


def _validate_bindings(
    *,
    decision_id: str,
    signal: AlphaSignal,
    strategy_artifact: StrategyArtifactReference,
    target: TargetPortfolio,
    capacity_review: PortfolioCapacityReview,
    sizing_decision: SizingDecision,
    mandate: StrategyRiskMandate,
    pre_trade_request: PreTradeAutonomyRequest,
) -> None:
    if not str(decision_id).strip() or target.decision_id != decision_id or capacity_review.decision_id != decision_id:
        raise BoundShadowRiskEvidenceError("decision_id must match target and capacity review")
    if strategy_artifact.strategy_id != signal.strategy_id.lower():
        raise BoundShadowRiskEvidenceError("strategy artifact strategy mismatch")
    if strategy_artifact.risk_mandate is None:
        raise BoundShadowRiskEvidenceError("strategy artifact risk mandate is required")
    if strategy_artifact.risk_mandate != mandate.to_reference():
        raise BoundShadowRiskEvidenceError("strategy artifact mandate reference mismatch")
    sizing_blocker = research_sizing_blocker(
        sizing_decision,
        target=target,
        capacity_review=capacity_review,
        strategy_artifact=strategy_artifact,
        market=signal.market,
    )
    if sizing_blocker is not None:
        raise BoundShadowRiskEvidenceError(f"sizing decision invalid: {sizing_blocker}")
    if target.generated_at != signal.available_at or capacity_review.decision_at != signal.available_at:
        raise BoundShadowRiskEvidenceError("target, capacity and signal times must match")
    if not strategy_artifact.risk_mandate.is_current(signal.available_at):
        raise BoundShadowRiskEvidenceError("strategy artifact risk mandate is expired")
    if pre_trade_request.strategy_id.lower() != signal.strategy_id.lower():
        raise BoundShadowRiskEvidenceError("pre-trade request strategy mismatch")
    if pre_trade_request.symbol.upper() != signal.market.symbol:
        raise BoundShadowRiskEvidenceError("pre-trade request market mismatch")
    if pre_trade_request.evaluated_at != signal.available_at:
        raise BoundShadowRiskEvidenceError("pre-trade evaluation time must equal signal availability")
    if signal.expected_edge_bps is None:
        raise BoundShadowRiskEvidenceError("signal expected edge is required for pre-trade review")
    if not math.isclose(
        pre_trade_request.estimated_edge_bps,
        float(signal.expected_edge_bps),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise BoundShadowRiskEvidenceError("pre-trade request expected edge mismatch")
    expected_notional = _target_notional(target, capacity_review, signal.market.symbol)
    if not math.isclose(pre_trade_request.notional_eur, expected_notional, rel_tol=0.0, abs_tol=1e-12):
        raise BoundShadowRiskEvidenceError("pre-trade request notional mismatch")


def _target_notional(target: TargetPortfolio, capacity_review: PortfolioCapacityReview, symbol: str) -> float:
    if capacity_review.status != "CAPACITY_OK":
        raise BoundShadowRiskEvidenceError("capacity review must be CAPACITY_OK")
    if target.decision_id != capacity_review.decision_id:
        raise BoundShadowRiskEvidenceError("target and capacity decision_id mismatch")
    target_notional = float(capacity_review.target_notionals_eur.get(symbol.upper(), 0.0))
    if not math.isfinite(target_notional) or target_notional <= 0.0:
        raise BoundShadowRiskEvidenceError("target notional missing after capacity review")
    return target_notional


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise BoundShadowRiskEvidenceError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _primitive(value: object) -> object:
    if isinstance(value, datetime):
        return _utc(value, "fingerprint timestamp").isoformat()
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    if isinstance(value, list):
        return [_primitive(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in sorted(value.items())}
    return value


def _decision_fingerprint(decision: AutonomyDecision) -> str:
    """Snapshot the mutable gate diagnostics before binding them to evidence."""

    payload = _primitive(asdict(decision))
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()
