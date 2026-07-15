"""Stable, versioned boundary contracts for AUTOBOT.

These contracts are intentionally side-effect free.  They describe facts that
move between data, research, portfolio, risk, execution, ledger and monitoring
layers; they do not submit orders or change runtime state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
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
class FeatureSnapshotReference:
    """Immutable point-in-time evidence for the features behind a strategy.

    The reference contains only reproducible research facts.  It deliberately
    has no filesystem path or execution permission: a future shadow intent
    must prove the feature bundle that produced it without relying on a
    mutable runtime directory.
    """

    feature_snapshot_id: str
    fingerprint: str
    snapshot_kind: str
    source_snapshot_id: str
    source_snapshot_fingerprint: str
    feature_registry_fingerprint: str
    feature_versions: Mapping[str, str]
    runtime_parity_proven: bool
    ingestion_time_unknown_count: int = 0
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "feature_snapshot_id",
            "fingerprint",
            "snapshot_kind",
            "source_snapshot_id",
            "source_snapshot_fingerprint",
            "feature_registry_fingerprint",
        ):
            object.__setattr__(self, field_name, _required(getattr(self, field_name), field_name))
        versions = {str(key).strip(): str(value).strip() for key, value in self.feature_versions.items()}
        if not versions or not all(versions.keys()) or not all(versions.values()):
            raise ValueError("feature snapshot feature_versions are required")
        unknown_count = int(self.ingestion_time_unknown_count)
        if unknown_count < 0:
            raise ValueError("ingestion_time_unknown_count must be non-negative")
        if not self.runtime_parity_proven:
            raise ValueError("feature snapshot runtime parity must be proven")
        if unknown_count:
            raise ValueError("feature snapshot cannot prove runtime parity with unknown ingestion time")
        object.__setattr__(self, "feature_versions", versions)
        object.__setattr__(self, "snapshot_kind", self.snapshot_kind.upper())
        object.__setattr__(self, "ingestion_time_unknown_count", unknown_count)


@dataclass(frozen=True)
class RiskMandateReference:
    """Immutable, non-authorizing evidence for a strategy risk mandate.

    A future shadow intent may only carry a mandate that was bound to the
    artifact at research time.  The reference deliberately cannot authorize
    paper capital or live trading; those transitions remain separate human
    decisions outside the contract layer.
    """

    mandate_id: str
    strategy_id: str
    fingerprint: str
    mode_allowed: str
    capital_max_eur: Decimal | float
    expires_at: str
    human_approved_required_for_risk_increase: bool
    paper_capital_allowed: bool = False
    live_allowed: bool = False
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        for field_name in ("mandate_id", "strategy_id", "fingerprint", "mode_allowed", "expires_at"):
            object.__setattr__(self, field_name, _required(getattr(self, field_name), field_name))
        capital_max_eur = float(self.capital_max_eur)
        if capital_max_eur < 0:
            raise ValueError("risk mandate capital_max_eur must be non-negative")
        try:
            expires_at = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("risk mandate expires_at must be ISO-8601") from exc
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("risk mandate expires_at must be timezone-aware")
        if self.paper_capital_allowed or self.live_allowed:
            raise ValueError("risk mandate reference cannot authorize paper or live")
        if not self.human_approved_required_for_risk_increase:
            raise ValueError("risk mandate reference must require human approval for risk increase")
        object.__setattr__(self, "strategy_id", self.strategy_id.lower())
        object.__setattr__(self, "mode_allowed", self.mode_allowed.lower())
        object.__setattr__(self, "capital_max_eur", capital_max_eur)
        object.__setattr__(self, "expires_at", expires_at.astimezone(timezone.utc).isoformat())

    def is_current(self, at: datetime) -> bool:
        """Return whether this immutable mandate was still valid at ``at``."""

        return _utc(at, "risk mandate evaluation time") <= datetime.fromisoformat(self.expires_at)


@dataclass(frozen=True)
class StrategyArtifactReference:
    """Immutable research artifact facts required by a future order intent.

    This reference deliberately carries no execution permission.  It binds an
    intent to the exact strategy artifact that supplied the strategy version,
    data snapshot and feature definitions, without importing the governance
    registry into the generic contract module.
    """

    artifact_id: str
    fingerprint: str
    strategy_id: str
    strategy_version: str
    code_commit: str
    data_snapshot_id: str
    feature_versions: Mapping[str, str]
    status: str
    feature_snapshots: tuple[FeatureSnapshotReference, ...] = ()
    risk_mandate: RiskMandateReference | None = None
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "artifact_id",
            "fingerprint",
            "strategy_id",
            "strategy_version",
            "code_commit",
            "data_snapshot_id",
            "status",
        ):
            object.__setattr__(self, field_name, _required(getattr(self, field_name), field_name))
        versions = {str(key).strip(): str(value).strip() for key, value in self.feature_versions.items()}
        if not versions or not all(versions.keys()) or not all(versions.values()):
            raise ValueError("artifact feature_versions are required")
        object.__setattr__(self, "strategy_id", self.strategy_id.lower())
        object.__setattr__(self, "status", self.status.upper())
        object.__setattr__(self, "feature_versions", versions)
        snapshots = tuple(self.feature_snapshots)
        if any(not isinstance(item, FeatureSnapshotReference) for item in snapshots):
            raise ValueError("artifact feature_snapshots must contain FeatureSnapshotReference values")
        snapshot_ids = [item.feature_snapshot_id for item in snapshots]
        if len(snapshot_ids) != len(set(snapshot_ids)):
            raise ValueError("artifact feature snapshot ids must be unique")
        if snapshots:
            snapshot_versions: dict[str, str] = {}
            for snapshot in snapshots:
                for feature_id, version in snapshot.feature_versions.items():
                    if feature_id in snapshot_versions:
                        raise ValueError("artifact feature snapshots cannot overlap feature versions")
                    snapshot_versions[feature_id] = version
            if snapshot_versions != versions:
                raise ValueError("artifact feature snapshot versions must match artifact feature_versions")
        if self.risk_mandate is not None:
            if not isinstance(self.risk_mandate, RiskMandateReference):
                raise ValueError("artifact risk_mandate must be a RiskMandateReference")
            if self.risk_mandate.strategy_id != self.strategy_id:
                raise ValueError("artifact risk mandate strategy_id must match artifact strategy_id")
        if self.status in {"SHADOW_ELIGIBLE", "SHADOW"} and self.risk_mandate is None:
            raise ValueError("shadow artifact risk mandate evidence is required")
        object.__setattr__(self, "feature_snapshots", snapshots)

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
    """Non-executable request that must pass independent risk review."""
    decision_id: str
    strategy_id: str
    strategy_artifact: StrategyArtifactReference
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
        if not isinstance(self.strategy_artifact, StrategyArtifactReference):
            raise ValueError("strategy_artifact must be a StrategyArtifactReference")
        if self.strategy_artifact.strategy_id != self.strategy_id.lower():
            raise ValueError("strategy_artifact strategy_id must match order intent strategy_id")
        if not self.strategy_artifact.feature_snapshots:
            raise ValueError("strategy_artifact feature snapshot evidence is required")
        if not all(snapshot.runtime_parity_proven for snapshot in self.strategy_artifact.feature_snapshots):
            raise ValueError("strategy_artifact feature snapshot runtime parity is required")
        if mode == "shadow" and self.strategy_artifact.risk_mandate is None:
            raise ValueError("strategy_artifact risk mandate evidence is required")
        if mode == "shadow" and not self.strategy_artifact.risk_mandate.is_current(created_at):
            raise ValueError("strategy_artifact risk mandate is expired")
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "execution_mode", mode)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "data_available_at", data_available_at)
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ExecutionCommand:
    """Executable command emitted only after a risk decision approves an intent."""

    command_id: str
    decision_id: str
    client_order_id: str
    risk_decision_id: str
    issued_at: datetime
    execution_mode: str
    approved_notional: Decimal | float
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        mode = _required(self.execution_mode, "execution_mode").lower()
        if mode not in {"paper", "live"}:
            raise ValueError("execution command mode must be paper or live")
        if float(self.approved_notional) <= 0:
            raise ValueError("approved_notional must be positive")
        for field_name in ("command_id", "decision_id", "client_order_id", "risk_decision_id"):
            object.__setattr__(self, field_name, _required(getattr(self, field_name), field_name))
        object.__setattr__(self, "issued_at", _utc(self.issued_at, "issued_at"))
        object.__setattr__(self, "execution_mode", mode)


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


def contract_to_dict(value: Any) -> dict[str, Any]:
    """Return a canonical JSON-safe representation of a boundary contract."""
    if not is_dataclass(value):
        raise TypeError("value must be a dataclass contract")
    return _primitive(asdict(value))


def contract_fingerprint(value: Any) -> str:
    """Stable fingerprint used by contract tests and reproducibility manifests."""
    payload = json.dumps(contract_to_dict(value), sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _primitive(value: Any) -> Any:
    if isinstance(value, datetime):
        return _utc(value, "timestamp").isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Mapping):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_primitive(item) for item in value]
    return value
