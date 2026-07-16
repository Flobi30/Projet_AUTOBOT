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
import math
from typing import TYPE_CHECKING, Mapping

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
    feature_versions: Mapping[str, str]
    markets: Mapping[str, MarketIdentity]
    source: str = "legacy_backtest_alpha_adapter/v1"

    def __post_init__(self) -> None:
        for field_name in ("strategy_id", "strategy_version", "data_snapshot_id", "source"):
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
) -> BacktestAlphaAdaptation:
    """Adapt one legacy signal without inventing market, timing or edge facts.

    ``buy`` becomes a long alpha only when the generator supplies an explicit
    finite positive ``expected_edge_bps`` metadata value.  A legacy
    ``gross_edge_bps`` is intentionally insufficient: it has not established a
    net expected edge.  ``sell`` becomes a flat/reduce-to-cash decision and
    never creates a short signal.
    """

    symbol = str(signal.symbol).strip().upper()
    market = provenance.markets.get(symbol)
    if market is None:
        raise BacktestAlphaAdapterError(f"explicit_market_mapping_missing:{symbol or 'unknown'}")
    decision_at = _utc_timestamp(signal.timestamp)
    side = str(signal.side).strip().lower()
    if side == "buy":
        direction = "long"
        portfolio_action = "ENTER_LONG"
        expected_edge_bps = _expected_edge_bps(signal.metadata)
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


def _expected_edge_bps(metadata: Mapping[str, object]) -> float:
    value = metadata.get("expected_edge_bps")
    if value is None:
        raise BacktestAlphaAdapterError("expected_edge_bps_missing_for_long_signal")
    try:
        expected_edge_bps = float(value)
    except (TypeError, ValueError) as exc:
        raise BacktestAlphaAdapterError("expected_edge_bps must be numeric") from exc
    if not math.isfinite(expected_edge_bps) or expected_edge_bps <= 0.0:
        raise BacktestAlphaAdapterError("expected_edge_bps must be positive and finite")
    return expected_edge_bps


def _utc_timestamp(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise BacktestAlphaAdapterError("legacy signal timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


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
