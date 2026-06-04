"""Research-only execution cost model for AUTOBOT validation."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


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

    taker_fee_bps: float = 16.0
    maker_fee_bps: float = 10.0
    fallback_spread_bps: float = 8.0
    slippage_bps: float = 4.0
    latency_buffer_bps: float = 1.0
    min_notional_eur: float = 5.0
    max_spread_bps: float = 80.0
    max_liquidity_participation: float = 0.05

    def validate(self) -> None:
        for field_name, value in asdict(self).items():
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"{field_name} must be finite")
            if float(value) < 0.0:
                raise ValueError(f"{field_name} cannot be negative")
        if self.max_liquidity_participation <= 0.0 or self.max_liquidity_participation > 1.0:
            raise ValueError("max_liquidity_participation must be in (0, 1]")

    def to_dict(self) -> dict[str, float]:
        return {key: float(value) for key, value in asdict(self).items()}


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
        return fee_bps + spread_bps + self.config.slippage_bps + self.config.latency_buffer_bps

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
        adverse_bps = (spread_bps / 2.0) + self.config.slippage_bps + self.config.latency_buffer_bps
        direction = 1.0 if request.normalized_side == "buy" else -1.0
        execution_price = request.price * (1.0 + direction * _bps_to_rate(adverse_bps))

        if request.normalized_order_type == "limit" and request.limit_price is not None:
            if request.normalized_side == "buy" and execution_price > request.limit_price:
                return self._rejected(request, "limit_price_not_reached", quantity, notional, spread_bps)
            if request.normalized_side == "sell" and execution_price < request.limit_price:
                return self._rejected(request, "limit_price_not_reached", quantity, notional, spread_bps)

        fee_eur = notional * _bps_to_rate(fee_bps)
        spread_cost_eur = notional * _bps_to_rate(spread_bps / 2.0)
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
        net = gross - fees
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
