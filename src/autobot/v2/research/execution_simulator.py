"""Contract-driven, research-only shadow execution simulation.

The simulator is intentionally isolated from the paper engine and order router.
It models conservative fills for a shadow ``OrderIntent`` and emits contracts
that can later be audited by a separate risk/OMS layer.  It never creates an
``ExecutionCommand`` and refuses paper or live intents.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import math
from typing import Mapping, Sequence

from autobot.v2.contracts import AlphaSignal, FillEvent, MarketIdentity, OrderEvent, OrderIntent, RiskDecision, contract_fingerprint

from .backtest_alpha_adapter import cost_model_fingerprint
from .execution_cost_model import ExecutionCostConfig, ExecutionCostModel, FillRequest, FillResult
from .microstructure_cost_evidence import MicrostructureCostEvidence


class ResearchExecutionError(ValueError):
    """Raised when a research-only simulation invariant is violated."""


@dataclass(frozen=True)
class MarketExecutionRules:
    """Explicit Kraken-like market constraints captured from public metadata."""

    symbol: str
    min_volume: float
    min_notional_eur: float
    volume_decimals: int
    price_decimals: int
    market: MarketIdentity
    source_snapshot_id: str
    source_fingerprint: str
    source: str = "kraken_asset_pairs_public"

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.source.strip():
            raise ResearchExecutionError("market rules symbol and source are required")
        if not isinstance(self.market, MarketIdentity):
            raise ResearchExecutionError("market rules require an explicit MarketIdentity")
        if self.market.symbol != self.symbol.upper():
            raise ResearchExecutionError("market rules symbol must match MarketIdentity.symbol")
        source_snapshot_id = str(self.source_snapshot_id).strip()
        source_fingerprint = str(self.source_fingerprint).strip().lower()
        if not source_snapshot_id:
            raise ResearchExecutionError("market rules source_snapshot_id is required")
        if not _is_sha256(source_fingerprint):
            raise ResearchExecutionError("market rules source_fingerprint must be a SHA-256 hex digest")
        for field_name in ("min_volume", "min_notional_eur"):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value <= 0.0:
                raise ResearchExecutionError(f"{field_name} must be positive and finite")
        for field_name in ("volume_decimals", "price_decimals"):
            value = int(getattr(self, field_name))
            if value < 0 or value > 16:
                raise ResearchExecutionError(f"{field_name} must be between zero and sixteen")
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "source_snapshot_id", source_snapshot_id)
        object.__setattr__(self, "source_fingerprint", source_fingerprint)

    @classmethod
    def from_kraken_asset_pair(
        cls,
        *,
        market: MarketIdentity,
        payload: Mapping[str, object],
        source_snapshot_id: str,
        source_fingerprint: str,
    ) -> "MarketExecutionRules":
        """Create rules from a cached public Kraken ``AssetPairs`` response."""

        return cls(
            symbol=market.symbol,
            min_volume=float(payload["ordermin"]),
            min_notional_eur=float(payload["costmin"]),
            volume_decimals=int(payload["lot_decimals"]),
            price_decimals=int(payload["pair_decimals"]),
            market=market,
            source_snapshot_id=source_snapshot_id,
            source_fingerprint=source_fingerprint,
            source="kraken_asset_pairs_public",
        )


@dataclass(frozen=True)
class ExecutionScenario:
    name: str
    fee_multiplier: float = 1.0
    spread_multiplier: float = 1.0
    slippage_multiplier: float = 1.0
    latency_multiplier: float = 1.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ResearchExecutionError("scenario name is required")
        for field_name in ("fee_multiplier", "spread_multiplier", "slippage_multiplier", "latency_multiplier"):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value < 1.0:
                raise ResearchExecutionError(f"{field_name} must be finite and at least one")


CENTRAL_SCENARIO = ExecutionScenario("central")
PESSIMISTIC_SCENARIO = ExecutionScenario(
    "pessimistic",
    fee_multiplier=1.10,
    spread_multiplier=1.30,
    slippage_multiplier=1.50,
    latency_multiplier=2.00,
)
STRESS_SCENARIO = ExecutionScenario(
    "stress",
    fee_multiplier=1.25,
    spread_multiplier=1.75,
    slippage_multiplier=2.00,
    latency_multiplier=3.00,
)
DEFAULT_EXECUTION_SCENARIOS = (CENTRAL_SCENARIO, PESSIMISTIC_SCENARIO, STRESS_SCENARIO)


@dataclass(frozen=True)
class ScenarioEdgeProjection:
    """One conservative projection of an already net-costed alpha edge.

    ``expected_edge_bps`` is the edge reported under the exact central cost
    profile.  A non-central scenario only deducts its *incremental* modeled
    round-trip cost, preventing the base costs from being counted twice.
    """

    scenario: str
    cost_model_fingerprint: str
    round_trip_cost_bps: float
    incremental_cost_bps: float
    projected_net_edge_bps: float
    passes: bool


@dataclass(frozen=True)
class ScenarioEdgeReview:
    """Research-only economic gate for a single immutable ``AlphaSignal``."""

    status: str
    reason: str
    signal_id: str
    data_snapshot_id: str
    base_cost_model_fingerprint: str
    projections: tuple[ScenarioEdgeProjection, ...]
    microstructure_cost_evidence_fingerprint: str | None = None
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    @property
    def pessimistic_passed(self) -> bool:
        return any(item.scenario == "pessimistic" and item.passes for item in self.projections)


def review_net_edge_scenarios(
    signal: AlphaSignal,
    *,
    base_cost_config: ExecutionCostConfig,
    scenarios: Sequence[ExecutionScenario] = DEFAULT_EXECUTION_SCENARIOS,
    min_projected_net_edge_bps: float = 0.0,
    microstructure_cost_evidence: MicrostructureCostEvidence | None = None,
) -> ScenarioEdgeReview:
    """Check one net edge against central, pessimistic and stress costs.

    This is an evidence gate, not a promotion path.  It requires the signal to
    declare the exact central-cost fingerprint that produced its net edge and
    fails closed on missing/changed provenance.  A positive central result is
    insufficient: the pessimistic projection must also remain positive before
    the contract shadow pipeline may simulate the signal.
    """

    base_cost_config.validate()
    threshold = float(min_projected_net_edge_bps)
    if not math.isfinite(threshold) or threshold < 0.0:
        raise ResearchExecutionError("min_projected_net_edge_bps must be finite and non-negative")
    names = tuple(item.name for item in scenarios)
    if not names or len(names) != len(set(names)):
        raise ResearchExecutionError("scenario names must be non-empty and unique")
    if "central" not in names or "pessimistic" not in names:
        raise ResearchExecutionError("central and pessimistic scenarios are required")

    base_fingerprint = cost_model_fingerprint(base_cost_config.to_dict())
    evidence_fingerprint = (
        microstructure_cost_evidence.evidence_fingerprint
        if microstructure_cost_evidence is not None
        else None
    )
    if microstructure_cost_evidence is not None:
        evidence_reason = microstructure_cost_evidence.validation_reason_for_signal(
            signal,
            base_cost_config=base_cost_config,
        )
        if evidence_reason is not None:
            return ScenarioEdgeReview(
                "SCENARIO_EDGE_BLOCKED",
                evidence_reason,
                signal.signal_id,
                signal.data_snapshot_id,
                base_fingerprint,
                (),
                evidence_fingerprint,
            )
    declared_fingerprint = str(signal.metadata.get("cost_model_fingerprint") or "").strip()
    edge = signal.expected_edge_bps
    if edge is None or not math.isfinite(float(edge)) or float(edge) <= 0.0:
        return ScenarioEdgeReview(
            "SCENARIO_EDGE_BLOCKED",
            "net_expected_edge_missing",
            signal.signal_id,
            signal.data_snapshot_id,
            base_fingerprint,
            (),
            evidence_fingerprint,
        )
    if declared_fingerprint != base_fingerprint:
        return ScenarioEdgeReview(
            "SCENARIO_EDGE_BLOCKED",
            "cost_model_fingerprint_mismatch",
            signal.signal_id,
            signal.data_snapshot_id,
            base_fingerprint,
            (),
            evidence_fingerprint,
        )

    central_cost = base_cost_config.round_trip_cost_estimate_bps()
    projections: list[ScenarioEdgeProjection] = []
    for scenario in scenarios:
        scenario_config = scenario_cost_config(base_cost_config, scenario)
        scenario_cost = scenario_config.round_trip_cost_estimate_bps()
        incremental_cost = max(0.0, scenario_cost - central_cost)
        projected = float(edge) - incremental_cost
        projections.append(
            ScenarioEdgeProjection(
                scenario=scenario.name,
                cost_model_fingerprint=cost_model_fingerprint(scenario_config.to_dict()),
                round_trip_cost_bps=scenario_cost,
                incremental_cost_bps=incremental_cost,
                projected_net_edge_bps=projected,
                passes=projected > threshold,
            )
        )
    pessimistic = next(item for item in projections if item.scenario == "pessimistic")
    if not pessimistic.passes:
        return ScenarioEdgeReview(
            "SCENARIO_EDGE_BLOCKED",
            "pessimistic_net_edge_not_positive",
            signal.signal_id,
            signal.data_snapshot_id,
            base_fingerprint,
            tuple(projections),
            evidence_fingerprint,
        )
    return ScenarioEdgeReview(
        "SCENARIO_EDGE_OK",
        "pessimistic_net_edge_positive",
        signal.signal_id,
        signal.data_snapshot_id,
        base_fingerprint,
        tuple(projections),
        evidence_fingerprint,
    )


@dataclass(frozen=True)
class ShadowMarketSnapshot:
    """One point-in-time market input for a non-executable shadow fill.

    A simulator must not use a bare price timestamp: doing so can silently
    cross venues or use a price before the process could have known it.  The
    snapshot therefore mirrors the canonical data boundary and carries the
    exact market plus immutable source evidence.
    """

    market: MarketIdentity
    event_time: datetime
    available_time: datetime
    ingestion_time: datetime
    source_snapshot_id: str
    source_fingerprint: str
    price: float
    bid: float | None = None
    ask: float | None = None
    liquidity_eur: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.market, MarketIdentity):
            raise ResearchExecutionError("snapshot market must be a MarketIdentity")
        event_time = _utc(self.event_time, "snapshot event_time")
        available_time = _utc(self.available_time, "snapshot available_time")
        ingestion_time = _utc(self.ingestion_time, "snapshot ingestion_time")
        if available_time < event_time:
            raise ResearchExecutionError("snapshot available_time cannot precede event_time")
        if ingestion_time < available_time:
            raise ResearchExecutionError("snapshot ingestion_time cannot precede available_time")
        source_snapshot_id = str(self.source_snapshot_id).strip()
        source_fingerprint = str(self.source_fingerprint).strip().lower()
        if not source_snapshot_id:
            raise ResearchExecutionError("snapshot source_snapshot_id is required")
        if not _is_sha256(source_fingerprint):
            raise ResearchExecutionError("snapshot source_fingerprint must be a SHA-256 hex digest")
        if not math.isfinite(float(self.price)) or float(self.price) <= 0.0:
            raise ResearchExecutionError("snapshot price must be positive and finite")
        for field_name in ("bid", "ask", "liquidity_eur"):
            value = getattr(self, field_name)
            if value is not None and (not math.isfinite(float(value)) or float(value) <= 0.0):
                raise ResearchExecutionError(f"snapshot {field_name} must be positive and finite")
        if self.bid is not None and self.ask is not None and float(self.ask) < float(self.bid):
            raise ResearchExecutionError("snapshot ask cannot be below bid")
        object.__setattr__(self, "event_time", event_time)
        object.__setattr__(self, "available_time", available_time)
        object.__setattr__(self, "ingestion_time", ingestion_time)
        object.__setattr__(self, "source_snapshot_id", source_snapshot_id)
        object.__setattr__(self, "source_fingerprint", source_fingerprint)

    @property
    def usable_at(self) -> datetime:
        """Earliest time this AUTOBOT process may rely on the snapshot."""

        return max(self.available_time, self.ingestion_time)

    @property
    def fingerprint(self) -> str:
        """Stable identity used for idempotent research replay."""

        return contract_fingerprint(self)

    def provenance(self) -> dict[str, object]:
        return {
            "market": {
                "exchange": self.market.exchange,
                "market_type": self.market.market_type,
                "symbol": self.market.symbol,
                "base_asset": self.market.base_asset,
                "quote_asset": self.market.quote_asset,
            },
            "event_time": self.event_time.isoformat(),
            "available_time": self.available_time.isoformat(),
            "ingestion_time": self.ingestion_time.isoformat(),
            "source_snapshot_id": self.source_snapshot_id,
            "source_fingerprint": self.source_fingerprint,
            "snapshot_fingerprint": self.fingerprint,
            "price": self.price,
            "bid": self.bid,
            "ask": self.ask,
            "liquidity_eur": self.liquidity_eur,
        }


@dataclass(frozen=True)
class ResearchExecutionConfig:
    latency: timedelta = timedelta(seconds=1)
    max_market_age: timedelta = timedelta(minutes=2)
    allow_partial_fills: bool = True
    min_partial_notional_eur: float = 5.0
    scenario: ExecutionScenario = CENTRAL_SCENARIO
    require_market_rules: bool = True
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        if self.latency < timedelta(0) or self.max_market_age <= timedelta(0):
            raise ResearchExecutionError("latency must be non-negative and max_market_age positive")
        if not math.isfinite(float(self.min_partial_notional_eur)) or self.min_partial_notional_eur <= 0.0:
            raise ResearchExecutionError("min_partial_notional_eur must be positive and finite")
        if not self.research_only or self.paper_capital_allowed or self.live_allowed:
            raise ResearchExecutionError("research execution simulator cannot enable paper or live")


@dataclass(frozen=True)
class ResearchExecutionOutcome:
    client_order_id: str
    status: str
    reason: str
    requested_notional_eur: float
    filled_notional_eur: float
    unfilled_notional_eur: float
    order_events: tuple[OrderEvent, ...]
    fill: FillResult | None
    fill_event: FillEvent | None
    scenario: str
    risk_decision_id: str | None = None
    approved_notional_eur: float = 0.0
    market_snapshot_fingerprint: str | None = None
    market_snapshot_sequence_fingerprint: str | None = None
    execution_mode: str = "shadow"
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False


class ResearchExecutionSimulator:
    """Deterministic shadow simulator with idempotent client-order outcomes."""

    def __init__(
        self,
        *,
        cost_config: ExecutionCostConfig,
        config: ResearchExecutionConfig = ResearchExecutionConfig(),
        market_rules: Mapping[MarketIdentity, MarketExecutionRules] | None = None,
    ) -> None:
        self.config = config
        self.cost_config = scenario_cost_config(cost_config, config.scenario)
        self._cost_model = ExecutionCostModel(self.cost_config)
        normalized_rules: dict[MarketIdentity, MarketExecutionRules] = {}
        for market, rules in (market_rules or {}).items():
            if not isinstance(market, MarketIdentity):
                raise ResearchExecutionError("market_rules keys must be MarketIdentity values")
            if not isinstance(rules, MarketExecutionRules):
                raise ResearchExecutionError("market_rules values must be MarketExecutionRules")
            if market != rules.market:
                raise ResearchExecutionError("market_rules key must match the rules market identity")
            if rules.market in normalized_rules:
                raise ResearchExecutionError("market_rules cannot contain duplicate market identities")
            normalized_rules[rules.market] = rules
        self._market_rules = normalized_rules
        self._outcomes: dict[str, tuple[str, ResearchExecutionOutcome]] = {}

    def simulate(
        self,
        intent: OrderIntent,
        snapshots: Sequence[ShadowMarketSnapshot],
        *,
        risk_decision: RiskDecision | None,
    ) -> ResearchExecutionOutcome:
        """Simulate one intent using the first timely market snapshot after latency.

        A fill requires a matching, approved risk decision. Replaying the same
        client order id returns the original outcome only when the immutable
        intent/risk boundary is unchanged; a conflicting reuse is rejected.
        """

        snapshot_sequence_fingerprint = _snapshot_sequence_fingerprint(snapshots)
        idempotency_key = _idempotency_key(intent, risk_decision, snapshot_sequence_fingerprint)
        prior = self._outcomes.get(intent.client_order_id)
        if prior is not None:
            prior_key, prior_outcome = prior
            if prior_key == idempotency_key:
                return prior_outcome
            return self._terminal(
                intent,
                "REJECTED",
                "idempotency_conflict",
                (),
                intent.created_at,
                risk_decision=risk_decision,
                market_snapshot_sequence_fingerprint=snapshot_sequence_fingerprint,
            )
        outcome = self._simulate_once(
            intent,
            snapshots,
            risk_decision=risk_decision,
            market_snapshot_sequence_fingerprint=snapshot_sequence_fingerprint,
        )
        self._outcomes[intent.client_order_id] = (idempotency_key, outcome)
        return outcome

    def recover(
        self,
        intent: OrderIntent,
        snapshots: Sequence[ShadowMarketSnapshot],
        *,
        risk_decision: RiskDecision | None,
    ) -> ResearchExecutionOutcome:
        """Rebuild one outcome after a research-process restart without new orders."""

        return self.simulate(intent, snapshots, risk_decision=risk_decision)

    def _simulate_once(
        self,
        intent: OrderIntent,
        snapshots: Sequence[ShadowMarketSnapshot],
        *,
        risk_decision: RiskDecision | None,
        market_snapshot_sequence_fingerprint: str,
    ) -> ResearchExecutionOutcome:
        created = OrderEvent(intent.client_order_id, "CREATED", intent.created_at, reason="research_shadow_intent")
        if intent.execution_mode != "shadow":
            return self._terminal(
                intent,
                "REJECTED",
                "non_shadow_intent_not_allowed",
                (created,),
                intent.created_at,
                risk_decision=risk_decision,
                market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
            )
        risk_reason, approved_notional = _approved_notional(intent, risk_decision)
        if risk_reason is not None:
            return self._terminal(
                intent,
                "REJECTED",
                risk_reason,
                (created,),
                intent.created_at,
                risk_decision=risk_decision,
                market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
            )
        rules = self._market_rules.get(intent.market)
        if rules is None and self.config.require_market_rules:
            return self._terminal(
                intent,
                "REJECTED",
                "market_execution_rules_missing",
                (created,),
                intent.created_at,
                risk_decision=risk_decision,
                approved_notional=approved_notional,
                market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
            )
        submitted = OrderEvent(intent.client_order_id, "SUBMITTED", intent.created_at, reason="research_shadow_risk_approved")
        if any(snapshot.market != intent.market for snapshot in snapshots):
            return self._terminal(
                intent,
                "REJECTED",
                "market_snapshot_market_identity_mismatch",
                (created, submitted),
                intent.created_at,
                risk_decision=risk_decision,
                approved_notional=approved_notional,
                market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
            )
        ordered = _ordered_snapshots(snapshots)
        earliest = intent.created_at + self.config.latency * self.config.scenario.latency_multiplier
        snapshot = next((item for item in ordered if item.usable_at >= earliest), None)
        if snapshot is None:
            return self._terminal(
                intent,
                "EXPIRED",
                "no_market_after_latency",
                (created, submitted),
                intent.created_at,
                risk_decision=risk_decision,
                approved_notional=approved_notional,
                market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
            )
        if snapshot.usable_at - intent.created_at > self.config.max_market_age:
            return self._terminal(
                intent,
                "EXPIRED",
                "market_data_stale_before_fill",
                (created, submitted),
                snapshot.usable_at,
                risk_decision=risk_decision,
                approved_notional=approved_notional,
                market_snapshot_fingerprint=snapshot.fingerprint,
                market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
            )
        if snapshot.usable_at - snapshot.event_time > self.config.max_market_age:
            return self._terminal(
                intent,
                "EXPIRED",
                "market_snapshot_stale_at_availability",
                (created, submitted),
                snapshot.usable_at,
                risk_decision=risk_decision,
                approved_notional=approved_notional,
                market_snapshot_fingerprint=snapshot.fingerprint,
                market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
            )
        acknowledged = OrderEvent(intent.client_order_id, "ACKNOWLEDGED", snapshot.usable_at, reason="research_market_snapshot")
        requested = approved_notional
        available = snapshot.liquidity_eur
        if available is None:
            return self._terminal(
                intent,
                "REJECTED",
                "observed_liquidity_missing",
                (created, submitted, acknowledged),
                snapshot.usable_at,
                risk_decision=risk_decision,
                approved_notional=approved_notional,
                market_snapshot_fingerprint=snapshot.fingerprint,
                market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
            )
        maximum = float(available) * self.cost_config.max_liquidity_participation
        fill_notional = min(requested, maximum)
        if rules is not None:
            fill_notional = _quantized_notional(fill_notional, price=_requested_price(intent, snapshot), rules=rules)
            if fill_notional <= 0.0:
                return self._terminal(
                    intent,
                    "REJECTED",
                    "quantity_below_market_minimum",
                    (created, submitted, acknowledged),
                    snapshot.usable_at,
                    risk_decision=risk_decision,
                    approved_notional=approved_notional,
                    market_snapshot_fingerprint=snapshot.fingerprint,
                    market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
                )
            if fill_notional + 1e-12 < rules.min_notional_eur:
                return self._terminal(
                    intent,
                    "REJECTED",
                    "notional_below_market_minimum",
                    (created, submitted, acknowledged),
                    snapshot.usable_at,
                    risk_decision=risk_decision,
                    approved_notional=approved_notional,
                    market_snapshot_fingerprint=snapshot.fingerprint,
                    market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
                )
        partial = fill_notional + 1e-12 < requested
        if partial and (not self.config.allow_partial_fills or fill_notional < self.config.min_partial_notional_eur):
            return self._terminal(
                intent,
                "REJECTED",
                "insufficient_liquidity",
                (created, submitted, acknowledged),
                snapshot.usable_at,
                risk_decision=risk_decision,
                approved_notional=approved_notional,
                market_snapshot_fingerprint=snapshot.fingerprint,
                market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
            )
        order_type = str(intent.metadata.get("order_type") or "market").lower()
        if order_type not in {"market", "limit"}:
            return self._terminal(
                intent,
                "REJECTED",
                "unsupported_order_type",
                (created, submitted, acknowledged),
                snapshot.usable_at,
                risk_decision=risk_decision,
                approved_notional=approved_notional,
                market_snapshot_fingerprint=snapshot.fingerprint,
                market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
            )
        try:
            limit_price = _optional_float(intent.metadata.get("limit_price"))
        except (TypeError, ValueError, ResearchExecutionError):
            return self._terminal(
                intent,
                "REJECTED",
                "invalid_limit_price",
                (created, submitted, acknowledged),
                snapshot.usable_at,
                risk_decision=risk_decision,
                approved_notional=approved_notional,
                market_snapshot_fingerprint=snapshot.fingerprint,
                market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
            )
        if order_type == "limit" and limit_price is None:
            return self._terminal(
                intent,
                "REJECTED",
                "limit_price_required",
                (created, submitted, acknowledged),
                snapshot.usable_at,
                risk_decision=risk_decision,
                approved_notional=approved_notional,
                market_snapshot_fingerprint=snapshot.fingerprint,
                market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
            )
        request = FillRequest(
            symbol=intent.market.symbol,
            side=intent.side,
            price=_requested_price(intent, snapshot),
            notional_eur=fill_notional,
            timestamp=snapshot.usable_at,
            order_type=order_type,
            limit_price=limit_price,
            bid=snapshot.bid,
            ask=snapshot.ask,
            liquidity_eur=available,
            metadata={
                **dict(intent.metadata),
                "scenario": self.config.scenario.name,
                "execution_mode": "shadow",
                "market_snapshot": snapshot.provenance(),
                "market_snapshot_sequence_fingerprint": market_snapshot_sequence_fingerprint,
                "simulation_cost_model_fingerprint": cost_model_fingerprint(self.cost_config.to_dict()),
                "simulation_scenario": self.config.scenario.name,
            },
        )
        fill = self._cost_model.simulate_fill(request)
        if not fill.accepted:
            return self._terminal(
                intent,
                "REJECTED",
                fill.reason,
                (created, submitted, acknowledged),
                snapshot.usable_at,
                fill=fill,
                risk_decision=risk_decision,
                approved_notional=approved_notional,
                market_snapshot_fingerprint=snapshot.fingerprint,
                market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
            )
        fill_event = FillEvent(
            client_order_id=intent.client_order_id,
            fill_id=f"shadow_fill_{intent.client_order_id}",
            occurred_at=snapshot.usable_at,
            quantity=fill.quantity,
            average_price=fill.execution_price,
            fees=fill.fee_eur,
        )
        status = "PARTIALLY_FILLED" if partial else "FILLED"
        terminal = OrderEvent(intent.client_order_id, status, snapshot.usable_at, reason="research_shadow_fill")
        return ResearchExecutionOutcome(
            client_order_id=intent.client_order_id,
            status=status,
            reason="partial_fill" if partial else "filled",
            requested_notional_eur=requested,
            filled_notional_eur=fill.notional_eur,
            unfilled_notional_eur=max(0.0, requested - fill.notional_eur),
            order_events=(created, submitted, acknowledged, terminal),
            fill=fill,
            fill_event=fill_event,
            scenario=self.config.scenario.name,
            risk_decision_id=risk_decision.risk_decision_id if risk_decision else None,
            approved_notional_eur=approved_notional,
            market_snapshot_fingerprint=snapshot.fingerprint,
            market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
        )

    def _terminal(
        self,
        intent: OrderIntent,
        status: str,
        reason: str,
        events: tuple[OrderEvent, ...],
        occurred_at: datetime,
        *,
        fill: FillResult | None = None,
        risk_decision: RiskDecision | None = None,
        approved_notional: float = 0.0,
        market_snapshot_fingerprint: str | None = None,
        market_snapshot_sequence_fingerprint: str | None = None,
    ) -> ResearchExecutionOutcome:
        # ``EXPIRED`` is an outcome of this research simulator; the stable
        # boundary contract represents it as a cancellation with the precise
        # expiry reason retained in the outcome.
        event_type = "CANCELLED" if status == "EXPIRED" else status
        terminal = OrderEvent(intent.client_order_id, event_type, occurred_at, reason=reason)
        return ResearchExecutionOutcome(
            client_order_id=intent.client_order_id,
            status=status,
            reason=reason,
            requested_notional_eur=float(intent.target_notional),
            filled_notional_eur=0.0,
            unfilled_notional_eur=float(intent.target_notional),
            order_events=(*events, terminal),
            fill=fill,
            fill_event=None,
            scenario=self.config.scenario.name,
            risk_decision_id=risk_decision.risk_decision_id if risk_decision else None,
            approved_notional_eur=approved_notional,
            market_snapshot_fingerprint=market_snapshot_fingerprint,
            market_snapshot_sequence_fingerprint=market_snapshot_sequence_fingerprint,
        )


def scenario_cost_config(base: ExecutionCostConfig, scenario: ExecutionScenario) -> ExecutionCostConfig:
    """Return a conservative copy of the shared research cost model."""

    return replace(
        base,
        taker_fee_bps=base.taker_fee_bps * scenario.fee_multiplier,
        maker_fee_bps=base.maker_fee_bps * scenario.fee_multiplier,
        fallback_spread_bps=base.fallback_spread_bps * scenario.spread_multiplier,
        slippage_bps=base.slippage_bps * scenario.slippage_multiplier,
        latency_buffer_bps=base.latency_buffer_bps * scenario.latency_multiplier,
    )


def _requested_price(intent: OrderIntent, snapshot: ShadowMarketSnapshot) -> float:
    # With an atomic top-of-book snapshot, the mid is the neutral reference
    # from which the shared cost model charges half-spread plus slippage and
    # latency.  A last/mark price could be stale or lie on one side of the
    # current book, creating an accidental optimistic fill.  Without a book,
    # retain the explicit snapshot price and let the conservative fallback
    # spread apply.
    if snapshot.bid is not None and snapshot.ask is not None:
        return (float(snapshot.bid) + float(snapshot.ask)) / 2.0
    return float(snapshot.price)


def _approved_notional(intent: OrderIntent, risk_decision: RiskDecision | None) -> tuple[str | None, float]:
    if risk_decision is None:
        return "risk_decision_missing", 0.0
    if risk_decision.decision_id != intent.decision_id:
        return "risk_decision_intent_mismatch", 0.0
    if risk_decision.decided_at < intent.data_available_at:
        return "risk_decision_before_data_available", 0.0
    if not risk_decision.approved:
        return "risk_decision_not_approved", 0.0
    approved = (
        float(risk_decision.reduced_notional)
        if risk_decision.reduced_notional is not None
        else float(intent.target_notional)
    )
    if approved <= 0.0:
        return "risk_decision_reduced_notional_zero", 0.0
    if approved > float(intent.target_notional) + 1e-12:
        return "risk_decision_increases_requested_notional", 0.0
    return None, approved


def _idempotency_key(
    intent: OrderIntent,
    risk_decision: RiskDecision | None,
    market_snapshot_sequence_fingerprint: str,
) -> str:
    risk_component = contract_fingerprint(risk_decision) if risk_decision is not None else "risk_decision_missing"
    return f"{contract_fingerprint(intent)}:{risk_component}:{market_snapshot_sequence_fingerprint}"


def _snapshot_sequence_fingerprint(snapshots: Sequence[ShadowMarketSnapshot]) -> str:
    """Bind idempotency to every market input, not only the order intent."""

    payload = "|".join(snapshot.fingerprint for snapshot in _ordered_snapshots(snapshots))
    return sha256(payload.encode("utf-8")).hexdigest()


def _ordered_snapshots(snapshots: Sequence[ShadowMarketSnapshot]) -> tuple[ShadowMarketSnapshot, ...]:
    """Canonicalize replay inputs so equivalent sequences stay idempotent."""

    return tuple(
        sorted(
            snapshots,
            key=lambda item: (
                item.usable_at,
                item.event_time,
                item.source_snapshot_id,
                item.source_fingerprint,
            ),
        )
    )


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ResearchExecutionError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ResearchExecutionError("metadata price must be positive and finite")
    return result


def _quantized_notional(notional: float, *, price: float, rules: MarketExecutionRules) -> float:
    quantity = Decimal(str(notional)) / Decimal(str(price))
    increment = Decimal("1").scaleb(-rules.volume_decimals)
    quantized_quantity = quantity.quantize(increment, rounding=ROUND_DOWN)
    if float(quantized_quantity) + 1e-18 < rules.min_volume:
        return 0.0
    return float(quantized_quantity * Decimal(str(price)))
