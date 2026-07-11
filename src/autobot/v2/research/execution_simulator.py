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
import math
from typing import Mapping, Sequence

from autobot.v2.contracts import FillEvent, OrderEvent, OrderIntent

from .execution_cost_model import ExecutionCostConfig, ExecutionCostModel, FillRequest, FillResult


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
    source: str = "kraken_asset_pairs_public"

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.source.strip():
            raise ResearchExecutionError("market rules symbol and source are required")
        for field_name in ("min_volume", "min_notional_eur"):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value <= 0.0:
                raise ResearchExecutionError(f"{field_name} must be positive and finite")
        for field_name in ("volume_decimals", "price_decimals"):
            value = int(getattr(self, field_name))
            if value < 0 or value > 16:
                raise ResearchExecutionError(f"{field_name} must be between zero and sixteen")
        object.__setattr__(self, "symbol", self.symbol.upper())

    @classmethod
    def from_kraken_asset_pair(cls, *, symbol: str, payload: Mapping[str, object]) -> "MarketExecutionRules":
        """Create rules from a cached public Kraken ``AssetPairs`` response."""

        return cls(
            symbol=symbol,
            min_volume=float(payload["ordermin"]),
            min_notional_eur=float(payload["costmin"]),
            volume_decimals=int(payload["lot_decimals"]),
            price_decimals=int(payload["pair_decimals"]),
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
class ShadowMarketSnapshot:
    timestamp: datetime
    price: float
    bid: float | None = None
    ask: float | None = None
    liquidity_eur: float | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ResearchExecutionError("snapshot timestamp must be timezone-aware")
        if not math.isfinite(float(self.price)) or float(self.price) <= 0.0:
            raise ResearchExecutionError("snapshot price must be positive and finite")
        for field_name in ("bid", "ask", "liquidity_eur"):
            value = getattr(self, field_name)
            if value is not None and (not math.isfinite(float(value)) or float(value) <= 0.0):
                raise ResearchExecutionError(f"snapshot {field_name} must be positive and finite")
        if self.bid is not None and self.ask is not None and float(self.ask) < float(self.bid):
            raise ResearchExecutionError("snapshot ask cannot be below bid")
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(timezone.utc))


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
        market_rules: Mapping[str, MarketExecutionRules] | None = None,
    ) -> None:
        self.config = config
        self.cost_config = scenario_cost_config(cost_config, config.scenario)
        self._cost_model = ExecutionCostModel(self.cost_config)
        self._market_rules = {str(symbol).upper(): rules for symbol, rules in (market_rules or {}).items()}
        self._outcomes: dict[str, ResearchExecutionOutcome] = {}

    def simulate(self, intent: OrderIntent, snapshots: Sequence[ShadowMarketSnapshot]) -> ResearchExecutionOutcome:
        """Simulate one intent using the first timely market snapshot after latency.

        Replaying the same client order id returns the original outcome rather
        than creating a duplicate simulated fill.  A new simulator recovers the
        same deterministic outcome from the same intent and snapshots.
        """

        prior = self._outcomes.get(intent.client_order_id)
        if prior is not None:
            return prior
        outcome = self._simulate_once(intent, snapshots)
        self._outcomes[intent.client_order_id] = outcome
        return outcome

    def recover(self, intent: OrderIntent, snapshots: Sequence[ShadowMarketSnapshot]) -> ResearchExecutionOutcome:
        """Rebuild one outcome after a research-process restart without new orders."""

        return self.simulate(intent, snapshots)

    def _simulate_once(self, intent: OrderIntent, snapshots: Sequence[ShadowMarketSnapshot]) -> ResearchExecutionOutcome:
        created = OrderEvent(intent.client_order_id, "CREATED", intent.created_at, reason="research_shadow_intent")
        if intent.execution_mode != "shadow":
            return self._terminal(intent, "REJECTED", "non_shadow_intent_not_allowed", (created,), intent.created_at)
        rules = self._market_rules.get(intent.market.symbol.upper())
        if rules is None and self.config.require_market_rules:
            return self._terminal(intent, "REJECTED", "market_execution_rules_missing", (created,), intent.created_at)
        submitted = OrderEvent(intent.client_order_id, "SUBMITTED", intent.created_at, reason="research_shadow_submission")
        ordered = sorted(snapshots, key=lambda item: item.timestamp)
        earliest = intent.created_at + self.config.latency * self.config.scenario.latency_multiplier
        snapshot = next((item for item in ordered if item.timestamp >= earliest), None)
        if snapshot is None:
            return self._terminal(intent, "EXPIRED", "no_market_after_latency", (created, submitted), intent.created_at)
        if snapshot.timestamp - intent.created_at > self.config.max_market_age:
            return self._terminal(intent, "EXPIRED", "market_data_stale_before_fill", (created, submitted), snapshot.timestamp)
        acknowledged = OrderEvent(intent.client_order_id, "ACKNOWLEDGED", snapshot.timestamp, reason="research_market_snapshot")
        requested = float(intent.target_notional)
        available = snapshot.liquidity_eur
        if available is None:
            return self._terminal(intent, "REJECTED", "observed_liquidity_missing", (created, submitted, acknowledged), snapshot.timestamp)
        maximum = float(available) * self.cost_config.max_liquidity_participation
        fill_notional = min(requested, maximum)
        if rules is not None:
            fill_notional = _quantized_notional(fill_notional, price=_requested_price(intent, snapshot), rules=rules)
            if fill_notional <= 0.0:
                return self._terminal(intent, "REJECTED", "quantity_below_market_minimum", (created, submitted, acknowledged), snapshot.timestamp)
            if fill_notional + 1e-12 < rules.min_notional_eur:
                return self._terminal(intent, "REJECTED", "notional_below_market_minimum", (created, submitted, acknowledged), snapshot.timestamp)
        partial = fill_notional + 1e-12 < requested
        if partial and (not self.config.allow_partial_fills or fill_notional < self.config.min_partial_notional_eur):
            return self._terminal(intent, "REJECTED", "insufficient_liquidity", (created, submitted, acknowledged), snapshot.timestamp)
        request = FillRequest(
            symbol=intent.market.symbol,
            side=intent.side,
            price=_requested_price(intent, snapshot),
            notional_eur=fill_notional,
            timestamp=snapshot.timestamp,
            order_type=str(intent.metadata.get("order_type") or "market"),
            limit_price=_optional_float(intent.metadata.get("limit_price")),
            bid=snapshot.bid,
            ask=snapshot.ask,
            liquidity_eur=available,
            metadata={**dict(intent.metadata), "scenario": self.config.scenario.name, "execution_mode": "shadow"},
        )
        fill = self._cost_model.simulate_fill(request)
        if not fill.accepted:
            return self._terminal(intent, "REJECTED", fill.reason, (created, submitted, acknowledged), snapshot.timestamp, fill=fill)
        fill_event = FillEvent(
            client_order_id=intent.client_order_id,
            fill_id=f"shadow_fill_{intent.client_order_id}",
            occurred_at=snapshot.timestamp,
            quantity=fill.quantity,
            average_price=fill.execution_price,
            fees=fill.fee_eur,
        )
        status = "PARTIALLY_FILLED" if partial else "FILLED"
        terminal = OrderEvent(intent.client_order_id, status, snapshot.timestamp, reason="research_shadow_fill")
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
    configured = _optional_float(intent.metadata.get("requested_price"))
    return configured if configured is not None else float(snapshot.price)


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
