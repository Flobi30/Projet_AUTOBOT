"""Strict bridge from legacy research backtest signals to ``AlphaSignal``.

Legacy research generators still emit :class:`BacktestSignal`.  This module is
the deliberate migration boundary: it turns a legacy observation into the
stable strategy contract only when provenance, market identity and an explicit
expected edge are supplied.  It has no router, paper-engine or runtime
imports, and it never creates an order or a fill.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from autobot.v2.contracts import AlphaSignal, MarketIdentity

if TYPE_CHECKING:
    from .backtest_engine import BacktestSignal


class BacktestAlphaAdapterError(ValueError):
    """Raised when a legacy signal lacks evidence required by ``AlphaSignal``."""


@dataclass(frozen=True)
class BacktestSignalProvenance:
    """Immutable facts a legacy generator cannot infer for itself.

    ``markets`` is deliberately keyed by the exact AUTOBOT signal symbol.  The
    bridge refuses to infer a base asset, quote asset or market type from a
    symbol string, preventing silent USD/EUR or spot/perpetual mix-ups.
    """

    strategy_id: str
    strategy_version: str
    data_snapshot_id: str
    source_snapshot_fingerprint: str
    input_snapshot_fingerprint: str
    feature_versions: Mapping[str, str]
    markets: Mapping[str, MarketIdentity]
    source: str = "legacy_backtest_alpha_adapter/v1"

    def __post_init__(self) -> None:
        for field_name in (
            "strategy_id",
            "strategy_version",
            "data_snapshot_id",
            "source_snapshot_fingerprint",
            "input_snapshot_fingerprint",
            "source",
        ):
            if not str(getattr(self, field_name)).strip():
                raise BacktestAlphaAdapterError(f"{field_name} is required")
        feature_versions = {str(key).strip(): str(value).strip() for key, value in self.feature_versions.items()}
        if not feature_versions or not all(feature_versions.keys()) or not all(feature_versions.values()):
            raise BacktestAlphaAdapterError("feature_versions are required")
        normalized_markets: dict[str, MarketIdentity] = {}
        for symbol, market in self.markets.items():
            key = str(symbol).strip().upper()
            if not key or not isinstance(market, MarketIdentity):
                raise BacktestAlphaAdapterError("markets require explicit MarketIdentity values")
            if market.symbol != key:
                raise BacktestAlphaAdapterError("market mapping key must match MarketIdentity.symbol")
            normalized_markets[key] = market
        if not normalized_markets:
            raise BacktestAlphaAdapterError("at least one explicit market mapping is required")
        object.__setattr__(self, "strategy_id", str(self.strategy_id).strip().lower())
        object.__setattr__(self, "strategy_version", str(self.strategy_version).strip())
        object.__setattr__(self, "data_snapshot_id", str(self.data_snapshot_id).strip())
        object.__setattr__(self, "source_snapshot_fingerprint", str(self.source_snapshot_fingerprint).strip())
        object.__setattr__(self, "input_snapshot_fingerprint", str(self.input_snapshot_fingerprint).strip())
        object.__setattr__(self, "feature_versions", feature_versions)
        object.__setattr__(self, "markets", normalized_markets)
        object.__setattr__(self, "source", str(self.source).strip())


@dataclass(frozen=True)
class BacktestAlphaAdaptation:
    """One normalized strategy fact plus its non-executable portfolio action."""

    alpha_signal: AlphaSignal
    portfolio_action: str
    decision_price: float
    decision_at: datetime
    source: str
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        if self.portfolio_action not in {"ENTER_LONG", "REDUCE_TO_CASH"}:
            raise BacktestAlphaAdapterError("portfolio_action must be ENTER_LONG or REDUCE_TO_CASH")
        if not math.isfinite(float(self.decision_price)) or float(self.decision_price) <= 0.0:
            raise BacktestAlphaAdapterError("decision_price must be positive and finite")
        if self.decision_at.tzinfo is None or self.decision_at.utcoffset() is None:
            raise BacktestAlphaAdapterError("decision_at must be timezone-aware")
        if not self.research_only or self.paper_capital_allowed or self.live_allowed:
            raise BacktestAlphaAdapterError("legacy backtest adaptation is research-only")
        object.__setattr__(self, "decision_at", self.decision_at.astimezone(timezone.utc))


def adapt_backtest_signal_to_alpha(
    signal: BacktestSignal,
    *,
    provenance: BacktestSignalProvenance,
    available_at: datetime,
    cost_model_fingerprint: str,
) -> BacktestAlphaAdaptation:
    """Adapt one legacy signal without inventing market, timing or edge facts.

    ``buy`` becomes a long alpha only when the generator supplies an explicit
    finite positive ``net_expected_edge_bps`` tied to the exact cost-model
    fingerprint used by the replay. A legacy ``gross_edge_bps`` is
    intentionally insufficient. ``available_at`` must be an explicit
    point-in-time fact (normally the source bar close), never an assumed bar
    opening timestamp. ``sell`` becomes a flat/reduce-to-cash decision and
    never creates a short signal.
    """

    symbol = str(signal.symbol).strip().upper()
    market = provenance.markets.get(symbol)
    if market is None:
        raise BacktestAlphaAdapterError(f"explicit_market_mapping_missing:{symbol or 'unknown'}")
    source_event_at = _utc_timestamp(signal.timestamp)
    decision_at = _utc_timestamp(available_at)
    if decision_at < source_event_at:
        raise BacktestAlphaAdapterError("available_at cannot precede legacy signal timestamp")
    expected_cost_fingerprint = str(cost_model_fingerprint).strip()
    if not expected_cost_fingerprint:
        raise BacktestAlphaAdapterError("cost_model_fingerprint is required")
    side = str(signal.side).strip().lower()
    if side == "buy":
        direction = "long"
        portfolio_action = "ENTER_LONG"
        expected_edge_bps = _net_expected_edge_bps(
            signal.metadata,
            cost_model_fingerprint=expected_cost_fingerprint,
        )
    elif side == "sell":
        direction = "flat"
        portfolio_action = "REDUCE_TO_CASH"
        expected_edge_bps = None
    else:
        raise BacktestAlphaAdapterError("legacy signal side must be buy or sell")

    decision_price = float(signal.price)
    if not math.isfinite(decision_price) or decision_price <= 0.0:
        raise BacktestAlphaAdapterError("legacy signal price must be positive and finite")
    metadata = {
        **dict(signal.metadata),
        "source": provenance.source,
        "legacy_backtest_symbol": symbol,
        "legacy_backtest_side": side,
        "decision_price": decision_price,
        "decision_timestamp": decision_at.isoformat(),
        "source_event_timestamp": source_event_at.isoformat(),
        "data_available_at": decision_at.isoformat(),
        "source_snapshot_fingerprint": provenance.source_snapshot_fingerprint,
        "input_snapshot_fingerprint": provenance.input_snapshot_fingerprint,
        "cost_model_fingerprint": expected_cost_fingerprint,
        "order_type": str(signal.order_type),
        "limit_price": signal.limit_price,
        "quantity": signal.quantity,
        "notional_eur": signal.notional_eur,
        "research_only": True,
        "paper_capital_allowed": False,
        "live_allowed": False,
    }
    alpha_signal = AlphaSignal(
        strategy_id=provenance.strategy_id,
        strategy_version=provenance.strategy_version,
        signal_id=_signal_id(provenance, signal, decision_at),
        market=market,
        direction=direction,
        generated_at=decision_at,
        available_at=decision_at,
        feature_versions=provenance.feature_versions,
        data_snapshot_id=provenance.data_snapshot_id,
        expected_edge_bps=expected_edge_bps,
        metadata=metadata,
    )
    return BacktestAlphaAdaptation(
        alpha_signal=alpha_signal,
        portfolio_action=portfolio_action,
        decision_price=decision_price,
        decision_at=decision_at,
        source=provenance.source,
    )


def _net_expected_edge_bps(
    metadata: Mapping[str, object],
    *,
    cost_model_fingerprint: str,
) -> float:
    value = metadata.get("net_expected_edge_bps")
    if value is None:
        raise BacktestAlphaAdapterError("net_expected_edge_bps_missing_for_long_signal")
    try:
        expected_edge_bps = float(value)
    except (TypeError, ValueError) as exc:
        raise BacktestAlphaAdapterError("net_expected_edge_bps must be numeric") from exc
    if not math.isfinite(expected_edge_bps) or expected_edge_bps <= 0.0:
        raise BacktestAlphaAdapterError("net_expected_edge_bps must be positive and finite")
    declared_cost_fingerprint = str(metadata.get("cost_model_fingerprint") or "").strip()
    if declared_cost_fingerprint != cost_model_fingerprint:
        raise BacktestAlphaAdapterError("net_expected_edge_cost_model_mismatch")
    return expected_edge_bps


def _utc_timestamp(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise BacktestAlphaAdapterError("legacy signal timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def available_at_from_bar(bar: Any) -> datetime:
    """Return an explicit source-bar availability time for strict adaptation.

    Legacy ``MarketBar.timestamp`` often represents the bar opening.  A
    contract-enabled replay must therefore carry either ``available_time`` or
    ``bar_close_time`` metadata and never assume that the opening timestamp was
    observable after the bar closed.
    """

    metadata = getattr(bar, "metadata", {})
    if not isinstance(metadata, Mapping):
        raise BacktestAlphaAdapterError("bar availability metadata is required")
    for field_name in ("available_time", "bar_close_time"):
        value = metadata.get(field_name)
        if value in (None, ""):
            continue
        return _utc_timestamp(_parse_timestamp(value, field_name=field_name))
    raise BacktestAlphaAdapterError("explicit_bar_available_time_missing")


def fingerprint_backtest_bars(bars: Sequence[Any]) -> str:
    """Fingerprint the exact normalized research input without runtime noise.

    The digest includes OHLCV and explicit temporal facts, but excludes derived
    regime metadata so optional analysis labels do not silently change the
    source-data identity. It is calculated after loader filters and therefore
    binds the precise subset replayed by a validation run.
    """

    digest = sha256()
    rows = []
    for bar in bars:
        metadata = getattr(bar, "metadata", {})
        metadata = metadata if isinstance(metadata, Mapping) else {}
        rows.append(
            {
                "symbol": str(getattr(bar, "symbol", "")).strip().upper(),
                "timeframe": str(getattr(bar, "timeframe", "")).strip(),
                "timestamp": _utc_timestamp(getattr(bar, "timestamp", None)).isoformat(),
                "open": _stable_number(getattr(bar, "open", None), field_name="open"),
                "high": _stable_number(getattr(bar, "high", None), field_name="high"),
                "low": _stable_number(getattr(bar, "low", None), field_name="low"),
                "close": _stable_number(getattr(bar, "close", None), field_name="close"),
                "volume": _stable_number(getattr(bar, "volume", None), field_name="volume"),
                "event_time": _optional_timestamp_text(metadata.get("event_time")),
                "available_time": _optional_timestamp_text(metadata.get("available_time")),
                "bar_close_time": _optional_timestamp_text(metadata.get("bar_close_time")),
                "ingestion_time": _optional_timestamp_text(metadata.get("ingestion_time")),
                "source_snapshot_id": str(metadata.get("source_snapshot_id") or "").strip(),
                "market_mapping_status": str(metadata.get("market_mapping_status") or "").strip(),
            }
        )
    for row in sorted(rows, key=lambda item: (item["symbol"], item["timeframe"], item["timestamp"])):
        digest.update(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def cost_model_fingerprint(cost_config: Mapping[str, object]) -> str:
    """Stable identity for the cost assumptions behind a net-edge claim."""

    payload = json.dumps(dict(cost_config), sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _parse_timestamp(value: object, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise BacktestAlphaAdapterError(f"{field_name} must be an ISO-8601 timestamp") from exc


def _optional_timestamp_text(value: object) -> str | None:
    if value in (None, ""):
        return None
    return _utc_timestamp(_parse_timestamp(value, field_name="temporal metadata")).isoformat()


def _stable_number(value: object, *, field_name: str) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BacktestAlphaAdapterError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number):
        raise BacktestAlphaAdapterError(f"{field_name} must be finite")
    return format(number, ".17g")


def _signal_id(provenance: BacktestSignalProvenance, signal: BacktestSignal, decision_at: datetime) -> str:
    return "|".join(
        (
            provenance.strategy_id,
            provenance.strategy_version,
            signal.symbol.upper(),
            str(signal.side).lower(),
            decision_at.isoformat(),
            str(signal.reason).strip() or "legacy_backtest_signal",
        )
    )
