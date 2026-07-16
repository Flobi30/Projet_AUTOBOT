"""Research-only execution cost model for AUTOBOT validation."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from autobot.v2.cost_profiles import DEFAULT_RESEARCH_COST_PROFILE, get_cost_profile


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bps_to_rate(value: float) -> float:
    return float(value) / 10_000.0


def _finite_positive(value: float | None, *, field_name: str) -> float | None:
    if value is None:
        return None
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{field_name} must be positive and finite")
    return result


@dataclass(frozen=True)
class ExecutionCostConfig:
    """Configurable cost assumptions used by research replay/backtests."""

    cost_profile: str = DEFAULT_RESEARCH_COST_PROFILE
    taker_fee_bps: float = 40.0
    maker_fee_bps: float = 25.0
    fallback_spread_bps: float = 8.0
    slippage_bps: float = 4.0
    latency_buffer_bps: float = 1.0
    spread_model: str = "observed_top_of_book_or_8bps_fallback"
    slippage_model: str = "fixed_4bps_per_leg_plus_1bps_latency"
    market_spread_charge_fraction: float = 1.0
    limit_spread_charge_fraction: float = 1.0
    default_entry_order_type: str = "market"
    default_exit_order_type: str = "market"
    legacy: bool = False
    runtime_comparable: bool = True
    min_notional_eur: float = 5.0
    max_spread_bps: float = 80.0
    max_liquidity_participation: float = 0.05

    def validate(self) -> None:
        numeric_fields = {
            "taker_fee_bps",
            "maker_fee_bps",
            "fallback_spread_bps",
            "slippage_bps",
            "latency_buffer_bps",
            "market_spread_charge_fraction",
            "limit_spread_charge_fraction",
            "min_notional_eur",
            "max_spread_bps",
            "max_liquidity_participation",
        }
        for field_name, value in asdict(self).items():
            if field_name not in numeric_fields:
                continue
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"{field_name} must be finite")
            if float(value) < 0.0:
                raise ValueError(f"{field_name} cannot be negative")
        if self.max_liquidity_participation <= 0.0 or self.max_liquidity_participation > 1.0:
            raise ValueError("max_liquidity_participation must be in (0, 1]")
        if self.market_spread_charge_fraction > 1.0 or self.limit_spread_charge_fraction > 1.0:
            raise ValueError("spread charge fractions cannot exceed 1")
        if self.default_entry_order_type not in {"market", "limit"}:
            raise ValueError("default_entry_order_type must be market or limit")
        if self.default_exit_order_type not in {"market", "limit"}:
            raise ValueError("default_exit_order_type must be market or limit")

    def spread_charge_fraction(self, order_type: str) -> float:
        return self.limit_spread_charge_fraction if order_type == "limit" else self.market_spread_charge_fraction

    def fee_for_order_type(self, order_type: str) -> float:
        return self.maker_fee_bps if order_type == "limit" else self.taker_fee_bps

    def round_trip_cost_estimate_bps(self) -> float:
        entry_type = self.default_entry_order_type
        exit_type = self.default_exit_order_type
        spread_fraction = self.spread_charge_fraction(entry_type) / 2.0
        spread_fraction += self.spread_charge_fraction(exit_type) / 2.0
        return (
            self.fee_for_order_type(entry_type)
            + self.fee_for_order_type(exit_type)
            + (self.fallback_spread_bps * spread_fraction)
            + (2.0 * self.slippage_bps)
            + (2.0 * self.latency_buffer_bps)
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["round_trip_cost_estimate_bps"] = self.round_trip_cost_estimate_bps()
        return payload


def execution_cost_config_for_profile(
    profile_name: str = DEFAULT_RESEARCH_COST_PROFILE,
    *,
    fee_bps: float | None = None,
    spread_bps: float | None = None,
    slippage_bps: float | None = None,
    latency_buffer_bps: float | None = None,
) -> ExecutionCostConfig:
    """Build a research cost config while preserving the selected profile label."""

    profile = get_cost_profile(profile_name)
    entry_type = "limit" if profile.entry_liquidity == "maker" else "market"
    exit_type = "limit" if profile.exit_liquidity == "maker" else "market"
    taker_fee = profile.taker_fee_bps if fee_bps is None else float(fee_bps)
    return ExecutionCostConfig(
        cost_profile=profile.name,
        taker_fee_bps=taker_fee,
        maker_fee_bps=profile.maker_fee_bps,
        fallback_spread_bps=profile.fallback_spread_bps if spread_bps is None else float(spread_bps),
        slippage_bps=profile.slippage_bps_per_leg if slippage_bps is None else float(slippage_bps),
        latency_buffer_bps=(
            profile.latency_buffer_bps_per_leg
            if latency_buffer_bps is None
            else float(latency_buffer_bps)
        ),
        spread_model=profile.spread_model,
        slippage_model=profile.slippage_model,
        market_spread_charge_fraction=profile.spread_charge_fraction,
        limit_spread_charge_fraction=profile.spread_charge_fraction,
        default_entry_order_type=entry_type,
        default_exit_order_type=exit_type,
        legacy=profile.legacy,
        runtime_comparable=profile.runtime_comparable,
    )


@dataclass(frozen=True)
class FillRequest:
    symbol: str
    side: str
    price: float
    quantity: float | None = None
    notional_eur: float | None = None
    timestamp: datetime = field(default_factory=_utc_now)
    order_type: str = "market"
    limit_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    liquidity_eur: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        side = self.side.lower()
        if side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        order_type = self.order_type.lower()
        if order_type not in {"market", "limit"}:
            raise ValueError("order_type must be market or limit")
        _finite_positive(self.price, field_name="price")
        _finite_positive(self.quantity, field_name="quantity")
        _finite_positive(self.notional_eur, field_name="notional_eur")
        _finite_positive(self.limit_price, field_name="limit_price")
        _finite_positive(self.bid, field_name="bid")
        _finite_positive(self.ask, field_name="ask")
        _finite_positive(self.liquidity_eur, field_name="liquidity_eur")
        if self.quantity is None and self.notional_eur is None:
            raise ValueError("quantity or notional_eur is required")
        if self.bid and self.ask and self.ask < self.bid:
            raise ValueError("ask cannot be below bid")

    @property
    def normalized_side(self) -> str:
        return self.side.lower()

    @property
    def normalized_order_type(self) -> str:
        return self.order_type.lower()

    def requested_notional(self) -> float:
        if self.notional_eur is not None:
            return float(self.notional_eur)
        return float(self.quantity or 0.0) * float(self.price)

    def requested_quantity(self) -> float:
        if self.quantity is not None:
            return float(self.quantity)
        return float(self.notional_eur or 0.0) / float(self.price)


@dataclass(frozen=True)
class FillResult:
    accepted: bool
    reason: str
    symbol: str
    side: str
    order_type: str
    requested_price: float
    execution_price: float
    quantity: float
    notional_eur: float
    fee_eur: float
    spread_cost_eur: float
    slippage_eur: float
    latency_cost_eur: float
    total_cost_eur: float
    effective_cost_bps: float
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(frozen=True)
class RoundTripPnL:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float
    gross_pnl_eur: float
    net_pnl_eur: float
    fees_eur: float
    spread_cost_eur: float
    slippage_eur: float
    latency_cost_eur: float
    total_cost_eur: float
    return_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExecutionCostModel:
    """Apply conservative, explicit costs to simulated orders.

    This class is deliberately independent from Kraken/live execution. It is a
    research component used to avoid perfect fills in replay/backtests.
    """

    def __init__(self, config: ExecutionCostConfig | None = None) -> None:
        self.config = config or ExecutionCostConfig()
        self.config.validate()

    def observed_spread_bps(self, request: FillRequest) -> float:
        if request.bid is None or request.ask is None:
            return self.config.fallback_spread_bps
        mid = (request.bid + request.ask) / 2.0
        if mid <= 0.0:
            return self.config.fallback_spread_bps
        return max(0.0, ((request.ask - request.bid) / mid) * 10_000.0)

    def estimate_cost_bps(self, request: FillRequest) -> float:
        spread_bps = max(self.config.fallback_spread_bps, self.observed_spread_bps(request))
        fee_bps = (
            self.config.maker_fee_bps
            if request.normalized_order_type == "limit"
            else self.config.taker_fee_bps
        )
        spread_cost_bps = (
            spread_bps
            * self.config.spread_charge_fraction(request.normalized_order_type)
            / 2.0
        )
        return fee_bps + spread_cost_bps + self.config.slippage_bps + self.config.latency_buffer_bps

    def simulate_fill(self, request: FillRequest) -> FillResult:
        notional = request.requested_notional()
        quantity = request.requested_quantity()
        spread_bps = max(self.config.fallback_spread_bps, self.observed_spread_bps(request))
        if notional < self.config.min_notional_eur:
            return self._rejected(request, "below_min_notional", quantity, notional, spread_bps)
        if spread_bps > self.config.max_spread_bps:
            return self._rejected(request, "spread_above_max", quantity, notional, spread_bps)
        if (
            request.liquidity_eur is not None
            and notional > request.liquidity_eur * self.config.max_liquidity_participation
        ):
            return self._rejected(request, "insufficient_liquidity", quantity, notional, spread_bps)

        fee_bps = (
            self.config.maker_fee_bps
            if request.normalized_order_type == "limit"
            else self.config.taker_fee_bps
        )
        spread_cost_bps = (
            spread_bps
            * self.config.spread_charge_fraction(request.normalized_order_type)
            / 2.0
        )
        adverse_bps = spread_cost_bps + self.config.slippage_bps + self.config.latency_buffer_bps
        direction = 1.0 if request.normalized_side == "buy" else -1.0
        execution_price = request.price * (1.0 + direction * _bps_to_rate(adverse_bps))

        if request.normalized_order_type == "limit" and request.limit_price is not None:
            if request.normalized_side == "buy" and execution_price > request.limit_price:
                return self._rejected(request, "limit_price_not_reached", quantity, notional, spread_bps)
            if request.normalized_side == "sell" and execution_price < request.limit_price:
                return self._rejected(request, "limit_price_not_reached", quantity, notional, spread_bps)

        fee_eur = notional * _bps_to_rate(fee_bps)
        spread_cost_eur = notional * _bps_to_rate(spread_cost_bps)
        slippage_eur = notional * _bps_to_rate(self.config.slippage_bps)
        latency_cost_eur = notional * _bps_to_rate(self.config.latency_buffer_bps)
        total_cost = fee_eur + spread_cost_eur + slippage_eur + latency_cost_eur
        effective_cost_bps = (total_cost / notional) * 10_000.0 if notional else 0.0
        return FillResult(
            accepted=True,
            reason="filled",
            symbol=request.symbol,
            side=request.normalized_side,
            order_type=request.normalized_order_type,
            requested_price=request.price,
            execution_price=execution_price,
            quantity=quantity,
            notional_eur=notional,
            fee_eur=fee_eur,
            spread_cost_eur=spread_cost_eur,
            slippage_eur=slippage_eur,
            latency_cost_eur=latency_cost_eur,
            total_cost_eur=total_cost,
            effective_cost_bps=effective_cost_bps,
            timestamp=request.timestamp,
            metadata=dict(request.metadata),
        )

    def round_trip_pnl(self, entry: FillResult, exit_fill: FillResult) -> RoundTripPnL:
        if not entry.accepted or not exit_fill.accepted:
            raise ValueError("round trip requires accepted entry and exit fills")
        if entry.symbol != exit_fill.symbol:
            raise ValueError("entry and exit symbols must match")
        quantity = min(entry.quantity, exit_fill.quantity)
        if entry.side == "buy":
            gross = (exit_fill.execution_price - entry.execution_price) * quantity
        else:
            gross = (entry.execution_price - exit_fill.execution_price) * quantity
        fees = entry.fee_eur + exit_fill.fee_eur
        spread = entry.spread_cost_eur + exit_fill.spread_cost_eur
        slippage = entry.slippage_eur + exit_fill.slippage_eur
        latency = entry.latency_cost_eur + exit_fill.latency_cost_eur
        total_cost = fees + spread + slippage + latency
        # Every modeled execution cost is an economic cost of the round trip.
        # Deducting commissions alone would make the research simulator more
        # optimistic than its own spread/slippage/latency assumptions.
        net = gross - total_cost
        basis = max(entry.notional_eur, 1e-12)
        return RoundTripPnL(
            symbol=entry.symbol,
            side=entry.side,
            quantity=quantity,
            entry_price=entry.execution_price,
            exit_price=exit_fill.execution_price,
            gross_pnl_eur=gross,
            net_pnl_eur=net,
            fees_eur=fees,
            spread_cost_eur=spread,
            slippage_eur=slippage,
            latency_cost_eur=latency,
            total_cost_eur=total_cost,
            return_pct=(net / basis) * 100.0,
        )

    def _rejected(
        self,
        request: FillRequest,
        reason: str,
        quantity: float,
        notional: float,
        spread_bps: float,
    ) -> FillResult:
        return FillResult(
            accepted=False,
            reason=reason,
            symbol=request.symbol,
            side=request.normalized_side,
            order_type=request.normalized_order_type,
            requested_price=request.price,
            execution_price=request.price,
            quantity=quantity,
            notional_eur=notional,
            fee_eur=0.0,
            spread_cost_eur=0.0,
            slippage_eur=0.0,
            latency_cost_eur=0.0,
            total_cost_eur=0.0,
            effective_cost_bps=spread_bps,
            timestamp=request.timestamp,
            metadata=dict(request.metadata),
        )
