"""Stable, versioned boundary contracts for AUTOBOT.

These contracts are intentionally side-effect free.  They describe facts that
move between data, research, portfolio, risk, execution, ledger and monitoring
layers; they do not submit orders or change runtime state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

CONTRACT_VERSION = 1


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _required(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


@dataclass(frozen=True)
class MarketIdentity:
    """Explicit market identity; adapters must never infer quote currency."""

    exchange: str
    market_type: str
    symbol: str
    base_asset: str
    quote_asset: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "exchange", _required(self.exchange, "exchange").lower())
        object.__setattr__(self, "market_type", _required(self.market_type, "market_type").lower())
        object.__setattr__(self, "symbol", _required(self.symbol, "symbol").upper())
        object.__setattr__(self, "base_asset", _required(self.base_asset, "base_asset").upper())
        object.__setattr__(self, "quote_asset", _required(self.quote_asset, "quote_asset").upper())


@dataclass(frozen=True)
class CanonicalMarketEvent:
    """Canonical market observation with point-in-time provenance."""

    market: MarketIdentity
    event_time: datetime
    available_time: datetime
    ingestion_time: datetime
    source_snapshot_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        event_time = _utc(self.event_time, "event_time")
        available_time = _utc(self.available_time, "available_time")
        ingestion_time = _utc(self.ingestion_time, "ingestion_time")
        if available_time < event_time:
            raise ValueError("available_time cannot precede event_time")
        if ingestion_time < available_time:
            raise ValueError("ingestion_time cannot precede available_time")
        object.__setattr__(self, "event_time", event_time)
        object.__setattr__(self, "available_time", available_time)
        object.__setattr__(self, "ingestion_time", ingestion_time)
        object.__setattr__(self, "source_snapshot_id", _required(self.source_snapshot_id, "source_snapshot_id"))
        object.__setattr__(self, "payload", dict(self.payload))


@dataclass(frozen=True)
class FeatureValue:
    feature_id: str
    feature_version: str
    market: MarketIdentity
    timeframe: str
    event_time: datetime
    available_time: datetime
    source_snapshot_id: str
    value: Decimal | float | int | None
    status: str = "ready"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        event_time = _utc(self.event_time, "event_time")
        available_time = _utc(self.available_time, "available_time")
        if available_time < event_time:
            raise ValueError("feature available_time cannot precede event_time")
        object.__setattr__(self, "feature_id", _required(self.feature_id, "feature_id"))
        object.__setattr__(self, "feature_version", _required(self.feature_version, "feature_version"))
        object.__setattr__(self, "timeframe", _required(self.timeframe, "timeframe"))
        object.__setattr__(self, "source_snapshot_id", _required(self.source_snapshot_id, "source_snapshot_id"))
        object.__setattr__(self, "event_time", event_time)
        object.__setattr__(self, "available_time", available_time)
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class AlphaSignal:
    strategy_id: str
    strategy_version: str
    signal_id: str
    market: MarketIdentity
    direction: str
    generated_at: datetime
    available_at: datetime
    feature_versions: Mapping[str, str]
    data_snapshot_id: str
    expected_edge_bps: Decimal | float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        generated_at = _utc(self.generated_at, "generated_at")
        available_at = _utc(self.available_at, "available_at")
        if available_at < generated_at:
            raise ValueError("signal available_at cannot precede generated_at")
        direction = _required(self.direction, "direction").lower()
        if direction not in {"long", "short", "flat"}:
            raise ValueError("direction must be long, short or flat")
        for field_name in ("strategy_id", "strategy_version", "signal_id", "data_snapshot_id"):
            object.__setattr__(self, field_name, _required(getattr(self, field_name), field_name))
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "generated_at", generated_at)
        object.__setattr__(self, "available_at", available_at)
        object.__setattr__(self, "feature_versions", dict(self.feature_versions))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class TargetPortfolio:
    decision_id: str
    generated_at: datetime
    target_weights: Mapping[str, Decimal | float]
    reserve_cash_weight: Decimal | float
    rationale: Mapping[str, str] = field(default_factory=dict)
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        generated_at = _utc(self.generated_at, "generated_at")
        reserve = float(self.reserve_cash_weight)
        weights = {str(symbol).upper(): float(weight) for symbol, weight in self.target_weights.items()}
        if reserve < 0 or any(weight < 0 for weight in weights.values()):
            raise ValueError("portfolio weights must be non-negative")
        if sum(weights.values()) + reserve > 1.000001:
            raise ValueError("target weights plus reserve cannot exceed 1")
        object.__setattr__(self, "decision_id", _required(self.decision_id, "decision_id"))
        object.__setattr__(self, "generated_at", generated_at)
        object.__setattr__(self, "target_weights", weights)
        object.__setattr__(self, "reserve_cash_weight", reserve)
        object.__setattr__(self, "rationale", dict(self.rationale))


@dataclass(frozen=True)
class OrderIntent:
    decision_id: str
    strategy_id: str
    market: MarketIdentity
    side: str
    target_notional: Decimal | float
    created_at: datetime
    data_available_at: datetime
    execution_mode: str
    client_order_id: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        created_at = _utc(self.created_at, "created_at")
        data_available_at = _utc(self.data_available_at, "data_available_at")
        if created_at < data_available_at:
            raise ValueError("order intent cannot be created before data is available")
        side = _required(self.side, "side").lower()
        if side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if float(self.target_notional) <= 0:
            raise ValueError("target_notional must be positive")
        mode = _required(self.execution_mode, "execution_mode").lower()
        if mode not in {"shadow", "paper", "live"}:
            raise ValueError("execution_mode must be shadow, paper or live")
        for field_name in ("decision_id", "strategy_id", "client_order_id"):
            object.__setattr__(self, field_name, _required(getattr(self, field_name), field_name))
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "execution_mode", mode)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "data_available_at", data_available_at)
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class RiskDecision:
    decision_id: str
    approved: bool
    decided_at: datetime
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    reduced_notional: Decimal | float | None = None
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not self.approved and not self.reasons:
            raise ValueError("rejected risk decision requires at least one reason")
        if self.reduced_notional is not None and float(self.reduced_notional) < 0:
            raise ValueError("reduced_notional must be non-negative")
        object.__setattr__(self, "decision_id", _required(self.decision_id, "decision_id"))
        object.__setattr__(self, "decided_at", _utc(self.decided_at, "decided_at"))


@dataclass(frozen=True)
class OrderEvent:
    client_order_id: str
    event_type: str
    occurred_at: datetime
    reason: str | None = None
    exchange_order_id: str | None = None
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        event_type = _required(self.event_type, "event_type").upper()
        if event_type not in {"CREATED", "SUBMITTED", "ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED", "UNKNOWN"}:
            raise ValueError("unsupported order event type")
        object.__setattr__(self, "client_order_id", _required(self.client_order_id, "client_order_id"))
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at, "occurred_at"))


@dataclass(frozen=True)
class FillEvent:
    client_order_id: str
    fill_id: str
    occurred_at: datetime
    quantity: Decimal | float
    average_price: Decimal | float
    fees: Decimal | float
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if float(self.quantity) <= 0 or float(self.average_price) <= 0 or float(self.fees) < 0:
            raise ValueError("fill quantity/price must be positive and fees non-negative")
        object.__setattr__(self, "client_order_id", _required(self.client_order_id, "client_order_id"))
        object.__setattr__(self, "fill_id", _required(self.fill_id, "fill_id"))
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at, "occurred_at"))


@dataclass(frozen=True)
class PositionSnapshot:
    position_id: str
    market: MarketIdentity
    quantity: Decimal | float
    average_entry_price: Decimal | float | None
    observed_at: datetime
    source: str
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.average_entry_price is not None and float(self.average_entry_price) <= 0:
            raise ValueError("average_entry_price must be positive when present")
        object.__setattr__(self, "position_id", _required(self.position_id, "position_id"))
        object.__setattr__(self, "source", _required(self.source, "source"))
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))


@dataclass(frozen=True)
class LedgerEntry:
    ledger_id: str
    entry_type: str
    occurred_at: datetime
    strategy_id: str | None
    decision_id: str | None
    client_order_id: str | None
    source: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "ledger_id", _required(self.ledger_id, "ledger_id"))
        object.__setattr__(self, "entry_type", _required(self.entry_type, "entry_type").upper())
        object.__setattr__(self, "source", _required(self.source, "source"))
        if self.strategy_id is not None:
            object.__setattr__(self, "strategy_id", _required(self.strategy_id, "strategy_id"))
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at, "occurred_at"))
        object.__setattr__(self, "payload", dict(self.payload))
