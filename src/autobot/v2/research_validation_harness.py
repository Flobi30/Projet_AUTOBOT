"""Event-driven replay harness for AUTOBOT strategy validation.

The harness is intentionally isolated from runtime paper/live execution. It
replays saved market data through strategy adapters, opportunity scoring,
research-only risk checks, simulated fills, a replay ledger, metrics and
baselines. It never submits Kraken orders and never promotes a strategy live.
"""

from __future__ import annotations

import csv
import json
import math
import random
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from .opportunity_scoring import OpportunityConfig, OpportunityResult, OpportunityScorer
from .strategies import SignalType, TradingSignal
from .strategy_validation_registry import StrategyAcceptanceCriteria


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), timezone.utc)
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _bps(value: float) -> float:
    return float(value) / 10_000.0


@dataclass(frozen=True)
class MarketEvent:
    timestamp: datetime
    symbol: str
    price: float
    volume: float = 0.0
    bid: float | None = None
    ask: float | None = None
    liquidity_eur: float | None = None
    timeframe: str = "tick"
    regime: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any], *, default_symbol: str | None = None) -> "MarketEvent":
        symbol = str(row.get("symbol") or row.get("pair") or default_symbol or "UNKNOWN")
        timestamp = _parse_timestamp(row.get("timestamp") or row.get("time") or row.get("date"))
        price = _safe_float(row.get("price") or row.get("close") or row.get("last"))
        if price <= 0:
            raise ValueError(f"invalid market event price for {symbol}: {price}")
        return cls(
            timestamp=timestamp,
            symbol=symbol,
            price=price,
            volume=_safe_float(row.get("volume"), 0.0),
            bid=_optional_positive(row.get("bid")),
            ask=_optional_positive(row.get("ask")),
            liquidity_eur=_optional_positive(row.get("liquidity_eur") or row.get("depth_eur")),
            timeframe=str(row.get("timeframe") or "tick"),
            regime=str(row["regime"]) if row.get("regime") not in (None, "") else None,
            metadata={k: v for k, v in row.items() if k not in {"timestamp", "time", "date", "symbol", "pair", "price", "close", "last", "volume", "bid", "ask", "liquidity_eur", "depth_eur", "timeframe", "regime"}},
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(frozen=True)
class SignalEvent:
    run_id: str
    strategy_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    reason: str
    timestamp: datetime
    order_type: str = "market"
    limit_price: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_trading_signal(
        cls,
        signal: TradingSignal,
        *,
        run_id: str,
        strategy_id: str,
        market_timestamp: datetime | None = None,
    ) -> "SignalEvent":
        side = "buy" if signal.type == SignalType.BUY else "sell"
        metadata = dict(signal.metadata or {})
        return cls(
            run_id=run_id,
            strategy_id=str(metadata.get("strategy") or strategy_id),
            symbol=signal.symbol,
            side=side,
            price=float(signal.price),
            quantity=float(signal.volume or 0.0),
            reason=signal.reason,
            timestamp=market_timestamp or signal.timestamp,
            order_type=str(metadata.get("order_type") or "market"),
            limit_price=_optional_positive(metadata.get("limit_price")),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(frozen=True)
class OpportunityScoreEvent:
    signal: SignalEvent
    result: OpportunityResult

    def to_dict(self) -> dict[str, Any]:
        return {"signal": self.signal.to_dict(), "result": self.result.to_dict()}


@dataclass(frozen=True)
class RiskDecision:
    accepted: bool
    reason: str
    signal: SignalEvent
    opportunity: OpportunityResult | None = None
    order_notional_eur: float = 0.0
    quantity: float = 0.0
    checks: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "signal": self.signal.to_dict(),
            "opportunity": self.opportunity.to_dict() if self.opportunity else None,
            "order_notional_eur": round(self.order_notional_eur, 8),
            "quantity": round(self.quantity, 12),
            "checks": dict(self.checks),
        }


@dataclass(frozen=True)
class SimulatedOrder:
    order_id: str
    run_id: str
    strategy_id: str
    symbol: str
    side: str
    order_type: str
    requested_price: float
    requested_quantity: float
    notional_eur: float
    timestamp: datetime
    limit_price: float | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(frozen=True)
class SimulatedFill:
    order_id: str
    run_id: str
    strategy_id: str
    symbol: str
    side: str
    status: str
    reason: str
    requested_price: float
    execution_price: float
    quantity: float
    notional_eur: float
    fee_eur: float
    slippage_eur: float
    spread_cost_eur: float
    timestamp: datetime
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def filled(self) -> bool:
        return self.status == "filled"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(frozen=True)
class LedgerEntry:
    run_id: str
    strategy_id: str
    symbol: str
    side: str
    timestamp: datetime
    quantity: float
    entry_price: float | None = None
    exit_price: float | None = None
    fees_eur: float = 0.0
    slippage_eur: float = 0.0
    gross_pnl_eur: float = 0.0
    net_pnl_eur: float = 0.0
    equity_eur: float = 0.0
    drawdown_eur: float = 0.0
    entry_reason: str = ""
    exit_reason: str = ""
    order_id: str = ""
    position_id: str = ""
    duration_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_closing_leg(self) -> bool:
        return self.side == "sell" and self.exit_price is not None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(frozen=True)
class StrategyMetrics:
    strategy_id: str
    run_id: str
    symbol: str
    initial_capital_eur: float
    final_equity_eur: float
    realized_gross_pnl_eur: float
    realized_net_pnl_eur: float
    total_net_pnl_eur: float
    total_return_gross_pct: float
    total_return_net_pct: float
    max_drawdown_eur: float
    max_drawdown_pct: float
    profit_factor: float | None
    winrate_pct: float
    expectancy_eur: float
    trade_count: int
    average_win_eur: float
    average_loss_eur: float
    average_trade_duration_seconds: float | None
    sharpe: float | None
    sortino: float | None
    total_fees_eur: float
    total_slippage_eur: float
    by_regime: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["profit_factor"] = _finite_or_none(self.profit_factor)
        data["sharpe"] = _finite_or_none(self.sharpe)
        data["sortino"] = _finite_or_none(self.sortino)
        return data


@dataclass(frozen=True)
class BaselineResult:
    name: str
    net_pnl_eur: float
    total_return_net_pct: float
    trade_count: int
    profit_factor: float | None
    max_drawdown_pct: float
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["profit_factor"] = _finite_or_none(self.profit_factor)
        return data


@dataclass(frozen=True)
class HarnessValidationDecision:
    status: str
    reason: str
    recommended_registry_status: str
    live_promotion_allowed: bool
    checks: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationRunResult:
    run_id: str
    strategy_id: str
    symbol: str
    started_at: datetime
    ended_at: datetime
    dataset_id: str
    hypothesis: str
    metrics: StrategyMetrics
    baselines: list[BaselineResult]
    decision: HarnessValidationDecision
    ledger: list[LedgerEntry]
    rejected_signals: list[RiskDecision]
    registry_update_proposal: dict[str, Any]
    market_event_count: int = 0
    signal_count: int = 0
    simulated_order_count: int = 0
    fill_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "dataset_id": self.dataset_id,
            "hypothesis": self.hypothesis,
            "metrics": self.metrics.to_dict(),
            "baselines": [item.to_dict() for item in self.baselines],
            "decision": self.decision.to_dict(),
            "market_event_count": self.market_event_count,
            "signal_count": self.signal_count,
            "simulated_order_count": self.simulated_order_count,
            "fill_count": self.fill_count,
            "ledger": [entry.to_dict() for entry in self.ledger],
            "rejected_signals": [decision.to_dict() for decision in self.rejected_signals],
            "registry_update_proposal": dict(self.registry_update_proposal),
        }


class ReplayStrategy(Protocol):
    strategy_id: str

    def on_market_event(self, event: MarketEvent) -> Sequence[SignalEvent]:
        ...

    def on_fill(self, fill: SimulatedFill) -> None:
        ...


class ReplayStrategyInstance:
    """Minimal instance facade used by existing AUTOBOT strategies in replay."""

    def __init__(self, symbol: str, initial_capital_eur: float) -> None:
        self.config = SimpleNamespace(symbol=symbol)
        self._capital = float(initial_capital_eur)
        self._positions: list[SimpleNamespace] = []

    def get_positions_snapshot(self) -> list[SimpleNamespace]:
        return list(self._positions)

    def get_current_capital(self) -> float:
        return self._capital

    def set_capital(self, capital: float) -> None:
        self._capital = float(capital)

    def apply_fill(self, fill: SimulatedFill) -> None:
        if not fill.filled:
            return
        if fill.side == "buy":
            self._positions.append(
                SimpleNamespace(
                    buy_price=fill.execution_price,
                    volume=fill.quantity,
                    symbol=fill.symbol,
                    status="open",
                )
            )
        elif fill.side == "sell":
            self._positions.clear()


class ExistingStrategyReplayAdapter:
    """Adapter for existing strategy objects exposing on_price and callbacks."""

    def __init__(
        self,
        *,
        strategy: Any,
        strategy_id: str,
        symbol: str,
        run_id: str,
        instance: ReplayStrategyInstance | None = None,
    ) -> None:
        self.strategy = strategy
        self.strategy_id = strategy_id
        self.symbol = symbol
        self.run_id = run_id
        self.instance = instance
        self._pending: list[TradingSignal] = []
        if hasattr(strategy, "set_signal_callback"):
            strategy.set_signal_callback(self._pending.append)

    def on_market_event(self, event: MarketEvent) -> Sequence[SignalEvent]:
        if event.symbol != self.symbol:
            return []
        self._pending.clear()
        if hasattr(self.strategy, "safe_on_price"):
            self.strategy.safe_on_price(event.price)
        elif hasattr(self.strategy, "on_price"):
            self.strategy.on_price(event.price)
        elif callable(self.strategy):
            produced = self.strategy(event)
            return list(produced or [])
        signals = [
            SignalEvent.from_trading_signal(
                signal,
                run_id=self.run_id,
                strategy_id=self.strategy_id,
                market_timestamp=event.timestamp,
            )
            for signal in self._pending
            if signal.type in {SignalType.BUY, SignalType.SELL, SignalType.CLOSE}
        ]
        return signals

    def on_fill(self, fill: SimulatedFill) -> None:
        if self.instance is not None:
            self.instance.apply_fill(fill)
        position = SimpleNamespace(buy_price=fill.execution_price, volume=fill.quantity)
        try:
            if fill.filled and fill.side == "buy" and hasattr(self.strategy, "on_position_opened"):
                self.strategy.on_position_opened(position)
            elif fill.filled and fill.side == "sell" and hasattr(self.strategy, "on_position_closed"):
                self.strategy.on_position_closed(position, fill.metadata.get("net_pnl_eur", 0.0))
        except Exception:
            # Replay should not crash because a legacy strategy notification is
            # incomplete. The fill remains recorded in the replay ledger.
            return


@dataclass(frozen=True)
class SimulatedExecutionConfig:
    fee_bps: float = 16.0
    spread_bps: float = 8.0
    slippage_bps: float = 4.0
    min_liquidity_eur: float = 10.0
    max_price_deviation_bps: float = 120.0
    latency_ms: int = 25
    allow_partial_fills: bool = False


@dataclass(frozen=True)
class ReplayRiskConfig:
    initial_capital_eur: float = 1_000.0
    risk_per_trade_pct: float = 10.0
    min_order_eur: float = 5.0
    max_order_eur: float = 100.0
    max_positions: int = 1
    max_symbol_exposure_pct: float = 50.0
    require_tradable_opportunity: bool = True


@dataclass
class ReplayPortfolio:
    initial_capital_eur: float
    cash_eur: float
    positions: list[dict[str, Any]] = field(default_factory=list)
    equity_eur: float = 0.0
    peak_equity_eur: float = 0.0

    @classmethod
    def create(cls, capital: float) -> "ReplayPortfolio":
        return cls(
            initial_capital_eur=float(capital),
            cash_eur=float(capital),
            equity_eur=float(capital),
            peak_equity_eur=float(capital),
        )

    def mark_to_market(self, price: float) -> float:
        position_value = sum(float(pos["quantity"]) * price for pos in self.positions)
        self.equity_eur = self.cash_eur + position_value
        self.peak_equity_eur = max(self.peak_equity_eur, self.equity_eur)
        return self.equity_eur

    @property
    def drawdown_eur(self) -> float:
        return max(0.0, self.peak_equity_eur - self.equity_eur)


class ReplayRiskEngine:
    def __init__(self, config: ReplayRiskConfig | None = None) -> None:
        self.config = config or ReplayRiskConfig()

    def evaluate(
        self,
        *,
        signal: SignalEvent,
        opportunity: OpportunityResult,
        portfolio: ReplayPortfolio,
        event: MarketEvent,
    ) -> RiskDecision:
        checks: dict[str, Any] = {
            "paper_replay_only": True,
            "live_order_allowed": False,
            "opportunity_status": opportunity.status,
        }
        if signal.side not in {"buy", "sell"}:
            return RiskDecision(False, "unsupported_signal_side", signal, opportunity, checks=checks)
        if self.config.require_tradable_opportunity and opportunity.status != "tradable":
            return RiskDecision(False, f"opportunity_{opportunity.reason}", signal, opportunity, checks=checks)

        if signal.side == "sell":
            if not portfolio.positions:
                return RiskDecision(False, "no_open_position", signal, opportunity, checks=checks)
            quantity = sum(float(pos["quantity"]) for pos in portfolio.positions)
            return RiskDecision(True, "risk_ok_close", signal, opportunity, quantity=quantity, checks=checks)

        if len(portfolio.positions) >= self.config.max_positions:
            return RiskDecision(False, "max_positions_reached", signal, opportunity, checks=checks)

        notional = self._order_notional(signal, portfolio)
        checks["requested_notional_eur"] = notional
        if notional < self.config.min_order_eur:
            return RiskDecision(False, "below_min_order_eur", signal, opportunity, notional, checks=checks)
        if notional > portfolio.cash_eur:
            return RiskDecision(False, "insufficient_cash", signal, opportunity, notional, checks=checks)

        max_symbol_exposure = portfolio.initial_capital_eur * self.config.max_symbol_exposure_pct / 100.0
        current_symbol_exposure = sum(
            float(pos["quantity"]) * event.price for pos in portfolio.positions if pos["symbol"] == signal.symbol
        )
        checks["symbol_exposure_after_eur"] = current_symbol_exposure + notional
        if current_symbol_exposure + notional > max_symbol_exposure:
            return RiskDecision(False, "symbol_exposure_limit", signal, opportunity, notional, checks=checks)

        quantity = notional / max(event.price, 1e-12)
        return RiskDecision(True, "risk_ok", signal, opportunity, notional, quantity, checks)

    def _order_notional(self, signal: SignalEvent, portfolio: ReplayPortfolio) -> float:
        requested = signal.quantity * signal.price if signal.quantity > 0 else 0.0
        if requested <= 0.0:
            requested = portfolio.initial_capital_eur * self.config.risk_per_trade_pct / 100.0
        return max(0.0, min(requested, self.config.max_order_eur, portfolio.cash_eur))


class SimulatedExecutionEngine:
    def __init__(self, config: SimulatedExecutionConfig | None = None) -> None:
        self.config = config or SimulatedExecutionConfig()

    def execute(self, order: SimulatedOrder, event: MarketEvent) -> SimulatedFill:
        bid, ask = self._book(event)
        liquidity = event.liquidity_eur if event.liquidity_eur is not None else max(order.notional_eur, self.config.min_liquidity_eur)
        if liquidity < self.config.min_liquidity_eur or liquidity < order.notional_eur:
            return self._rejected(order, event, "insufficient_liquidity")

        side_price = ask if order.side == "buy" else bid
        execution_price = side_price * (1.0 + _bps(self.config.slippage_bps if order.side == "buy" else -self.config.slippage_bps))
        if order.order_type == "limit":
            if order.limit_price is None:
                return self._rejected(order, event, "missing_limit_price")
            if order.side == "buy" and execution_price > order.limit_price:
                return self._rejected(order, event, "limit_price_not_reached")
            if order.side == "sell" and execution_price < order.limit_price:
                return self._rejected(order, event, "limit_price_not_reached")

        deviation_bps = abs(execution_price - order.requested_price) / order.requested_price * 10_000.0
        if deviation_bps > self.config.max_price_deviation_bps:
            return self._rejected(order, event, "price_deviation_too_large")

        quantity = order.requested_quantity
        if quantity <= 0 and order.notional_eur > 0:
            quantity = order.notional_eur / execution_price
        notional = quantity * execution_price
        fee = notional * _bps(self.config.fee_bps)
        slippage_eur = abs(execution_price - side_price) * quantity
        spread_cost_eur = abs(side_price - event.price) * quantity
        return SimulatedFill(
            order_id=order.order_id,
            run_id=order.run_id,
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            side=order.side,
            status="filled",
            reason="filled",
            requested_price=order.requested_price,
            execution_price=execution_price,
            quantity=quantity,
            notional_eur=notional,
            fee_eur=fee,
            slippage_eur=slippage_eur,
            spread_cost_eur=spread_cost_eur,
            timestamp=event.timestamp,
            latency_ms=self.config.latency_ms,
            metadata=dict(order.metadata),
        )

    def _book(self, event: MarketEvent) -> tuple[float, float]:
        if event.bid and event.ask and event.bid > 0 and event.ask >= event.bid:
            return event.bid, event.ask
        half = _bps(self.config.spread_bps) / 2.0
        return event.price * (1.0 - half), event.price * (1.0 + half)

    @staticmethod
    def _rejected(order: SimulatedOrder, event: MarketEvent, reason: str) -> SimulatedFill:
        return SimulatedFill(
            order_id=order.order_id,
            run_id=order.run_id,
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            side=order.side,
            status="rejected",
            reason=reason,
            requested_price=order.requested_price,
            execution_price=0.0,
            quantity=0.0,
            notional_eur=0.0,
            fee_eur=0.0,
            slippage_eur=0.0,
            spread_cost_eur=0.0,
            timestamp=event.timestamp,
            metadata=dict(order.metadata),
        )


class ReplayLedger:
    def __init__(self, run_id: str, strategy_id: str, initial_capital_eur: float) -> None:
        self.run_id = run_id
        self.strategy_id = strategy_id
        self.portfolio = ReplayPortfolio.create(initial_capital_eur)
        self.entries: list[LedgerEntry] = []
        self._position_seq = 0

    def apply_fill(self, fill: SimulatedFill, *, signal: SignalEvent, event: MarketEvent) -> LedgerEntry | None:
        if not fill.filled:
            return None
        self.portfolio.mark_to_market(event.price)
        if fill.side == "buy":
            total_cash_out = fill.notional_eur + fill.fee_eur
            if total_cash_out > self.portfolio.cash_eur + 1e-9:
                return None
            self._position_seq += 1
            position_id = f"{self.run_id}-pos-{self._position_seq}"
            self.portfolio.cash_eur -= total_cash_out
            self.portfolio.positions.append(
                {
                    "position_id": position_id,
                    "symbol": fill.symbol,
                    "quantity": fill.quantity,
                    "entry_price": fill.execution_price,
                    "entry_fee_eur": fill.fee_eur,
                    "entry_slippage_eur": fill.slippage_eur,
                    "entry_time": fill.timestamp,
                    "entry_reason": signal.reason,
                    "regime": event.regime or "unknown",
                }
            )
            equity = self.portfolio.mark_to_market(event.price)
            entry = LedgerEntry(
                run_id=self.run_id,
                strategy_id=self.strategy_id,
                symbol=fill.symbol,
                side="buy",
                timestamp=fill.timestamp,
                quantity=fill.quantity,
                entry_price=fill.execution_price,
                fees_eur=fill.fee_eur,
                slippage_eur=fill.slippage_eur,
                equity_eur=equity,
                drawdown_eur=self.portfolio.drawdown_eur,
                entry_reason=signal.reason,
                order_id=fill.order_id,
                position_id=position_id,
                metadata={"regime": event.regime or "unknown"},
            )
            self.entries.append(entry)
            return entry

        if not self.portfolio.positions:
            return None
        position = self.portfolio.positions.pop(0)
        quantity = min(fill.quantity, float(position["quantity"]))
        gross_pnl = (fill.execution_price - float(position["entry_price"])) * quantity
        fees = float(position["entry_fee_eur"]) + fill.fee_eur
        slippage = float(position["entry_slippage_eur"]) + fill.slippage_eur
        # Slippage is already baked into the execution prices. Keep it as a
        # cost attribution, but do not subtract it a second time from PnL.
        net_pnl = gross_pnl - fees
        self.portfolio.cash_eur += fill.notional_eur - fill.fee_eur
        equity = self.portfolio.mark_to_market(event.price)
        duration = (fill.timestamp - position["entry_time"]).total_seconds()
        entry = LedgerEntry(
            run_id=self.run_id,
            strategy_id=self.strategy_id,
            symbol=fill.symbol,
            side="sell",
            timestamp=fill.timestamp,
            quantity=quantity,
            entry_price=float(position["entry_price"]),
            exit_price=fill.execution_price,
            fees_eur=fees,
            slippage_eur=slippage,
            gross_pnl_eur=gross_pnl,
            net_pnl_eur=net_pnl,
            equity_eur=equity,
            drawdown_eur=self.portfolio.drawdown_eur,
            entry_reason=str(position["entry_reason"]),
            exit_reason=signal.reason,
            order_id=fill.order_id,
            position_id=str(position["position_id"]),
            duration_seconds=duration,
            metadata={"regime": position.get("regime", event.regime or "unknown")},
        )
        fill.metadata["net_pnl_eur"] = net_pnl
        self.entries.append(entry)
        return entry

    def export_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps([entry.to_dict() for entry in self.entries], indent=2), encoding="utf-8")

    def export_csv(self, path: str | Path) -> None:
        rows = [entry.to_dict() for entry in self.entries]
        with Path(path).open("w", newline="", encoding="utf-8") as handle:
            if not rows:
                handle.write("")
                return
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


class ReplayMetricsEngine:
    @staticmethod
    def calculate(
        *,
        run_id: str,
        strategy_id: str,
        symbol: str,
        initial_capital_eur: float,
        final_equity_eur: float,
        ledger: Sequence[LedgerEntry],
    ) -> StrategyMetrics:
        closing = [entry for entry in ledger if entry.is_closing_leg]
        pnl = [entry.net_pnl_eur for entry in closing]
        gross = [entry.gross_pnl_eur for entry in closing]
        wins = [value for value in pnl if value > 0]
        losses = [value for value in pnl if value < 0]
        gross_wins = sum(value for value in pnl if value > 0)
        gross_losses = abs(sum(value for value in pnl if value < 0))
        profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else (None if gross_wins <= 0 else float("inf"))
        trade_count = len(closing)
        expectancy = sum(pnl) / trade_count if trade_count else 0.0
        fees = sum(entry.fees_eur for entry in ledger)
        slippage = sum(entry.slippage_eur for entry in ledger)
        max_dd = max((entry.drawdown_eur for entry in ledger), default=0.0)
        durations = [entry.duration_seconds for entry in closing if entry.duration_seconds is not None]
        returns = [value / initial_capital_eur for value in pnl] if initial_capital_eur > 0 else []
        sharpe = _sharpe(returns)
        sortino = _sortino(returns)
        by_regime = _by_regime(closing)
        realized_gross_pnl = sum(gross)
        realized_net_pnl = sum(pnl)
        total_net_pnl = final_equity_eur - initial_capital_eur
        return StrategyMetrics(
            strategy_id=strategy_id,
            run_id=run_id,
            symbol=symbol,
            initial_capital_eur=initial_capital_eur,
            final_equity_eur=final_equity_eur,
            realized_gross_pnl_eur=realized_gross_pnl,
            realized_net_pnl_eur=realized_net_pnl,
            total_net_pnl_eur=total_net_pnl,
            total_return_gross_pct=(realized_gross_pnl / initial_capital_eur * 100.0) if initial_capital_eur else 0.0,
            total_return_net_pct=(total_net_pnl / initial_capital_eur * 100.0) if initial_capital_eur else 0.0,
            max_drawdown_eur=max_dd,
            max_drawdown_pct=(max_dd / initial_capital_eur * 100.0) if initial_capital_eur else 0.0,
            profit_factor=profit_factor,
            winrate_pct=(len(wins) / trade_count * 100.0) if trade_count else 0.0,
            expectancy_eur=expectancy,
            trade_count=trade_count,
            average_win_eur=sum(wins) / len(wins) if wins else 0.0,
            average_loss_eur=sum(losses) / len(losses) if losses else 0.0,
            average_trade_duration_seconds=sum(durations) / len(durations) if durations else None,
            sharpe=sharpe,
            sortino=sortino,
            total_fees_eur=fees,
            total_slippage_eur=slippage,
            by_regime=by_regime,
        )


class BaselineEngine:
    def __init__(self, execution_config: SimulatedExecutionConfig | None = None) -> None:
        self.execution_config = execution_config or SimulatedExecutionConfig()

    def evaluate(
        self,
        *,
        run_id: str,
        symbol: str,
        events: Sequence[MarketEvent],
        initial_capital_eur: float,
    ) -> list[BaselineResult]:
        return [
            self.no_trade(initial_capital_eur),
            self.buy_and_hold(run_id=run_id, symbol=symbol, events=events, initial_capital_eur=initial_capital_eur),
            self.random_signal(run_id=run_id, symbol=symbol, events=events, initial_capital_eur=initial_capital_eur),
        ]

    @staticmethod
    def no_trade(initial_capital_eur: float) -> BaselineResult:
        return BaselineResult(
            name="no_trade_baseline",
            net_pnl_eur=0.0,
            total_return_net_pct=0.0,
            trade_count=0,
            profit_factor=None,
            max_drawdown_pct=0.0,
            details={"initial_capital_eur": initial_capital_eur},
        )

    def buy_and_hold(
        self,
        *,
        run_id: str,
        symbol: str,
        events: Sequence[MarketEvent],
        initial_capital_eur: float,
    ) -> BaselineResult:
        if len(events) < 2:
            return BaselineResult("buy_and_hold", 0.0, 0.0, 0, None, 0.0, {"reason": "not_enough_events"})
        first, last = events[0], events[-1]
        exec_engine = SimulatedExecutionEngine(self.execution_config)
        qty = initial_capital_eur / max(first.price, 1e-12)
        buy = exec_engine.execute(
            SimulatedOrder(
                order_id=f"{run_id}-baseline-bh-buy",
                run_id=run_id,
                strategy_id="buy_and_hold",
                symbol=symbol,
                side="buy",
                order_type="market",
                requested_price=first.price,
                requested_quantity=qty,
                notional_eur=initial_capital_eur,
                timestamp=first.timestamp,
            ),
            first,
        )
        if not buy.filled:
            return BaselineResult("buy_and_hold", 0.0, 0.0, 0, None, 0.0, {"reason": buy.reason})
        sell = exec_engine.execute(
            SimulatedOrder(
                order_id=f"{run_id}-baseline-bh-sell",
                run_id=run_id,
                strategy_id="buy_and_hold",
                symbol=symbol,
                side="sell",
                order_type="market",
                requested_price=last.price,
                requested_quantity=buy.quantity,
                notional_eur=buy.quantity * last.price,
                timestamp=last.timestamp,
            ),
            last,
        )
        if not sell.filled:
            return BaselineResult("buy_and_hold", 0.0, 0.0, 0, None, 0.0, {"reason": sell.reason})
        net = sell.notional_eur - buy.notional_eur - buy.fee_eur - sell.fee_eur - buy.slippage_eur - sell.slippage_eur
        return BaselineResult(
            name="buy_and_hold",
            net_pnl_eur=net,
            total_return_net_pct=net / initial_capital_eur * 100.0,
            trade_count=1,
            profit_factor=None if net <= 0 else float("inf"),
            max_drawdown_pct=0.0,
            details={"first_price": first.price, "last_price": last.price, "fees_eur": buy.fee_eur + sell.fee_eur},
        )

    def random_signal(
        self,
        *,
        run_id: str,
        symbol: str,
        events: Sequence[MarketEvent],
        initial_capital_eur: float,
        seed: int = 7,
    ) -> BaselineResult:
        if len(events) < 4:
            return BaselineResult("random_signal_baseline", 0.0, 0.0, 0, None, 0.0, {"reason": "not_enough_events"})
        rng = random.Random(seed)
        exec_engine = SimulatedExecutionEngine(self.execution_config)
        cash = initial_capital_eur
        position_qty = 0.0
        entry_notional = 0.0
        pnls: list[float] = []
        for index, event in enumerate(events):
            if position_qty <= 0 and rng.random() < 0.08:
                notional = min(initial_capital_eur * 0.1, cash)
                order = SimulatedOrder(
                    order_id=f"{run_id}-baseline-random-buy-{index}",
                    run_id=run_id,
                    strategy_id="random_signal_baseline",
                    symbol=symbol,
                    side="buy",
                    order_type="market",
                    requested_price=event.price,
                    requested_quantity=notional / event.price,
                    notional_eur=notional,
                    timestamp=event.timestamp,
                )
                fill = exec_engine.execute(order, event)
                if fill.filled and fill.notional_eur + fill.fee_eur <= cash:
                    cash -= fill.notional_eur + fill.fee_eur
                    position_qty = fill.quantity
                    entry_notional = fill.notional_eur + fill.fee_eur + fill.slippage_eur
            elif position_qty > 0 and (rng.random() < 0.08 or index == len(events) - 1):
                order = SimulatedOrder(
                    order_id=f"{run_id}-baseline-random-sell-{index}",
                    run_id=run_id,
                    strategy_id="random_signal_baseline",
                    symbol=symbol,
                    side="sell",
                    order_type="market",
                    requested_price=event.price,
                    requested_quantity=position_qty,
                    notional_eur=position_qty * event.price,
                    timestamp=event.timestamp,
                )
                fill = exec_engine.execute(order, event)
                if fill.filled:
                    cash += fill.notional_eur - fill.fee_eur
                    net = fill.notional_eur - fill.fee_eur - fill.slippage_eur - entry_notional
                    pnls.append(net)
                    position_qty = 0.0
                    entry_notional = 0.0
        final_equity = cash + (position_qty * events[-1].price)
        losses = abs(sum(value for value in pnls if value < 0))
        wins = sum(value for value in pnls if value > 0)
        pf = wins / losses if losses > 0 else (None if wins <= 0 else float("inf"))
        return BaselineResult(
            name="random_signal_baseline",
            net_pnl_eur=final_equity - initial_capital_eur,
            total_return_net_pct=(final_equity - initial_capital_eur) / initial_capital_eur * 100.0,
            trade_count=len(pnls),
            profit_factor=pf,
            max_drawdown_pct=0.0,
            details={"seed": seed},
        )


@dataclass(frozen=True)
class ValidationHarnessConfig:
    run_id: str
    strategy_id: str
    symbol: str
    dataset_id: str = "inline"
    initial_capital_eur: float = 1_000.0
    hypothesis: str = "Replay validation run"
    timeframe: str = "tick"
    output_dir: Path = Path("reports/validation_runs")
    opportunity_config: OpportunityConfig = field(
        default_factory=lambda: OpportunityConfig(
            min_score=0.0,
            min_gross_edge_bps=0.0,
            min_net_edge_bps=-1_000.0,
            min_atr_bps=0.0,
            max_spread_bps=1_000.0,
            min_stability=0.0,
            pair_health_guard_enabled=False,
        )
    )
    risk_config: ReplayRiskConfig = field(default_factory=ReplayRiskConfig)
    execution_config: SimulatedExecutionConfig = field(default_factory=SimulatedExecutionConfig)
    acceptance_criteria: StrategyAcceptanceCriteria = field(default_factory=StrategyAcceptanceCriteria)


class ResearchValidationHarness:
    def __init__(
        self,
        config: ValidationHarnessConfig,
        *,
        scorer: OpportunityScorer | None = None,
        risk_engine: ReplayRiskEngine | None = None,
        execution_engine: SimulatedExecutionEngine | None = None,
    ) -> None:
        self.config = config
        self.scorer = scorer or OpportunityScorer(config.opportunity_config)
        self.risk = risk_engine or ReplayRiskEngine(config.risk_config)
        self.execution = execution_engine or SimulatedExecutionEngine(config.execution_config)
        self.metrics = ReplayMetricsEngine()
        self.baselines = BaselineEngine(config.execution_config)
        self._order_seq = 0

    def load_market_events_from_csv(
        self,
        path: str | Path,
        *,
        default_symbol: str | None = None,
    ) -> list[MarketEvent]:
        with Path(path).open("r", newline="", encoding="utf-8") as handle:
            return [MarketEvent.from_mapping(row, default_symbol=default_symbol) for row in csv.DictReader(handle)]

    def load_market_events_from_json(
        self,
        path: str | Path,
        *,
        default_symbol: str | None = None,
    ) -> list[MarketEvent]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = payload.get("events", payload) if isinstance(payload, Mapping) else payload
        if not isinstance(rows, list):
            raise ValueError("JSON dataset must be a list or an object with an events list")
        return [MarketEvent.from_mapping(row, default_symbol=default_symbol) for row in rows]

    def load_market_events_from_state_db(
        self,
        db_path: str | Path,
        *,
        symbol: str | None = None,
        symbols: Sequence[str] | None = None,
        start_at: Any | None = None,
        end_at: Any | None = None,
        limit: int | None = None,
    ) -> list[MarketEvent]:
        """Load recorded AUTOBOT market price samples from ``autobot_state.db``.

        These rows are runtime price observations captured by AUTOBOT. They are
        suitable replay inputs when enough samples exist, unlike trade ledgers
        which only reconstruct execution traces.
        """
        path = Path(db_path)
        if not path.exists():
            return []
        try:
            with closing(_connect_sqlite_readonly(path)) as conn:
                if not _sqlite_table_exists(conn, "market_price_samples"):
                    return []
                where, args = _sqlite_filters(
                    symbol_column="symbol",
                    time_column="observed_at",
                    symbols=_merge_symbols(symbol, symbols),
                    start_at=start_at,
                    end_at=end_at,
                )
                query = (
                    "SELECT sample_id, symbol, price, observed_at, bucket_start, source, created_at "
                    "FROM market_price_samples "
                    f"{where} "
                    "ORDER BY observed_at ASC, id ASC"
                )
                if limit is not None:
                    query += " LIMIT ?"
                    args.append(max(1, int(limit)))
                rows = conn.execute(query, args).fetchall()
        except Exception:
            return []

        events: list[MarketEvent] = []
        for row in rows:
            price = _safe_float(row["price"], 0.0)
            if price <= 0.0:
                continue
            events.append(
                MarketEvent(
                    timestamp=_parse_timestamp(row["observed_at"]),
                    symbol=str(row["symbol"] or "UNKNOWN").upper(),
                    price=price,
                    volume=0.0,
                    timeframe="runtime_sample",
                    metadata={
                        "source": "market_price_samples",
                        "sample_id": row["sample_id"],
                        "bucket_start": row["bucket_start"],
                        "sample_source": row["source"],
                        "created_at": row["created_at"],
                    },
                )
            )
        return events

    def load_market_events_from_trade_ledger(
        self,
        db_path: str | Path,
        *,
        symbol: str | None = None,
        symbols: Sequence[str] | None = None,
        include_opening: bool = True,
        include_closing: bool = True,
        start_at: Any | None = None,
        end_at: Any | None = None,
        limit: int | None = None,
    ) -> list[MarketEvent]:
        """Load execution-trace events from AUTOBOT ``trade_ledger`` rows.

        This is not a full market dataset: it only exposes prices where AUTOBOT
        actually recorded an opening or closing leg. It is useful for replay
        diagnostics and audit reconstruction, but strategy validation should
        prefer ``load_market_events_from_state_db`` when market samples exist.
        """
        return self._load_execution_trace_events(
            db_path,
            table="trade_ledger",
            source="trade_ledger_execution_trace",
            symbol=symbol,
            symbols=symbols,
            include_opening=include_opening,
            include_closing=include_closing,
            start_at=start_at,
            end_at=end_at,
            limit=limit,
        )

    def load_market_events_from_paper_trades_db(
        self,
        db_path: str | Path,
        *,
        symbol: str | None = None,
        symbols: Sequence[str] | None = None,
        statuses: Sequence[str] = ("filled", "closed"),
        start_at: Any | None = None,
        end_at: Any | None = None,
        limit: int | None = None,
    ) -> list[MarketEvent]:
        """Load execution-trace events from the paper executor trades table."""
        return self._load_execution_trace_events(
            db_path,
            table="trades",
            source="paper_trades_db_execution_trace",
            symbol=symbol,
            symbols=symbols,
            statuses=statuses,
            start_at=start_at,
            end_at=end_at,
            limit=limit,
        )

    def _load_execution_trace_events(
        self,
        db_path: str | Path,
        *,
        table: str,
        source: str,
        symbol: str | None = None,
        symbols: Sequence[str] | None = None,
        statuses: Sequence[str] | None = None,
        include_opening: bool = True,
        include_closing: bool = True,
        start_at: Any | None = None,
        end_at: Any | None = None,
        limit: int | None = None,
    ) -> list[MarketEvent]:
        path = Path(db_path)
        if not path.exists():
            return []
        try:
            with closing(_connect_sqlite_readonly(path)) as conn:
                if not _sqlite_table_exists(conn, table):
                    return []
                columns = _sqlite_columns(conn, table)
                time_column = "created_at" if "created_at" in columns else ("timestamp" if "timestamp" in columns else None)
                where, args = _sqlite_filters(
                    symbol_column="symbol" if "symbol" in columns else None,
                    time_column=time_column,
                    symbols=_merge_symbols(symbol, symbols),
                    start_at=start_at,
                    end_at=end_at,
                )
                if statuses and "status" in columns:
                    placeholders = ",".join("?" for _ in statuses)
                    where = f"{where} {'AND' if where else 'WHERE'} LOWER(status) IN ({placeholders})"
                    args.extend(str(status).lower() for status in statuses)
                order_column = time_column or ("id" if "id" in columns else "rowid")
                query = f"SELECT * FROM {table} {where} ORDER BY {order_column} ASC"
                if limit is not None:
                    query += " LIMIT ?"
                    args.append(max(1, int(limit)))
                rows = conn.execute(query, args).fetchall()
        except Exception:
            return []

        events: list[MarketEvent] = []
        for row in rows:
            if not _include_ledger_leg(row, include_opening=include_opening, include_closing=include_closing):
                continue
            price = _first_positive(row, ("executed_price", "price", "expected_price"))
            if price <= 0.0:
                continue
            volume = _safe_float(_row_get(row, "volume"), 0.0)
            timestamp = _row_get(row, "created_at") or _row_get(row, "timestamp")
            if timestamp in (None, ""):
                continue
            symbol_value = str(_row_get(row, "symbol") or "UNKNOWN").upper()
            events.append(
                MarketEvent(
                    timestamp=_parse_timestamp(timestamp),
                    symbol=symbol_value,
                    price=price,
                    volume=volume,
                    liquidity_eur=price * volume if volume > 0.0 else None,
                    timeframe="execution_trace",
                    metadata={
                        "source": source,
                        "table": table,
                        "side": _row_get(row, "side"),
                        "status": _row_get(row, "status"),
                        "txid": _row_get(row, "txid"),
                        "trade_id": _row_get(row, "trade_id") or _row_get(row, "id"),
                        "position_id": _row_get(row, "position_id"),
                        "instance_id": _row_get(row, "instance_id"),
                        "fees": _row_get(row, "fees"),
                        "slippage_bps": _row_get(row, "slippage_bps"),
                        "realized_pnl": _row_get(row, "realized_pnl") or _row_get(row, "profit"),
                        "is_opening_leg": _row_get(row, "is_opening_leg"),
                        "is_closing_leg": _row_get(row, "is_closing_leg"),
                    },
                )
            )
        return events

    def run(
        self,
        *,
        strategy: ReplayStrategy,
        market_events: Iterable[MarketEvent],
        write_report: bool = True,
    ) -> ValidationRunResult:
        events = self._sorted_events(market_events)
        if not events:
            raise ValueError("validation harness requires at least one market event")

        ledger = ReplayLedger(self.config.run_id, self.config.strategy_id, self.config.initial_capital_eur)
        rejected: list[RiskDecision] = []
        history_by_symbol: dict[str, list[tuple[datetime, float]]] = {}
        signal_count = 0
        simulated_order_count = 0
        fill_count = 0
        for event in events:
            history_by_symbol.setdefault(event.symbol, []).append((event.timestamp, event.price))
            ledger.portfolio.mark_to_market(event.price)
            for signal in strategy.on_market_event(event):
                signal_count += 1
                opportunity = self._score_signal(signal, event, ledger, history_by_symbol.get(event.symbol, []))
                risk = self.risk.evaluate(
                    signal=signal,
                    opportunity=opportunity.result,
                    portfolio=ledger.portfolio,
                    event=event,
                )
                if not risk.accepted:
                    rejected.append(risk)
                    continue
                order = self._order_from_risk(risk, event)
                simulated_order_count += 1
                fill = self.execution.execute(order, event)
                if not fill.filled:
                    rejected.append(
                        RiskDecision(False, fill.reason, signal, opportunity.result, checks={"execution_rejected": True})
                    )
                    continue
                fill_count += 1
                entry = ledger.apply_fill(fill, signal=signal, event=event)
                if entry is not None and hasattr(strategy, "on_fill"):
                    strategy.on_fill(fill)

        final_equity = ledger.portfolio.mark_to_market(events[-1].price)
        metrics = self.metrics.calculate(
            run_id=self.config.run_id,
            strategy_id=self.config.strategy_id,
            symbol=self.config.symbol,
            initial_capital_eur=self.config.initial_capital_eur,
            final_equity_eur=final_equity,
            ledger=ledger.entries,
        )
        baselines = self.baselines.evaluate(
            run_id=self.config.run_id,
            symbol=self.config.symbol,
            events=events,
            initial_capital_eur=self.config.initial_capital_eur,
        )
        decision = self._decide(metrics, baselines)
        result = ValidationRunResult(
            run_id=self.config.run_id,
            strategy_id=self.config.strategy_id,
            symbol=self.config.symbol,
            started_at=events[0].timestamp,
            ended_at=events[-1].timestamp,
            dataset_id=self.config.dataset_id,
            hypothesis=self.config.hypothesis,
            metrics=metrics,
            baselines=baselines,
            decision=decision,
            ledger=ledger.entries,
            rejected_signals=rejected,
            registry_update_proposal=self._registry_proposal(decision, metrics),
            market_event_count=len(events),
            signal_count=signal_count,
            simulated_order_count=simulated_order_count,
            fill_count=fill_count,
        )
        if write_report:
            self.write_report(result)
        return result

    @staticmethod
    def _sorted_events(market_events: Iterable[MarketEvent]) -> list[MarketEvent]:
        return sorted(market_events, key=lambda event: (event.timestamp, event.symbol))

    def _score_signal(
        self,
        signal: SignalEvent,
        event: MarketEvent,
        ledger: ReplayLedger,
        price_history: Sequence[tuple[datetime, float]],
    ) -> OpportunityScoreEvent:
        spread_bps = self._spread_bps(event)
        cost_bps = (self.config.execution_config.fee_bps * 2.0) + spread_bps + (self.config.execution_config.slippage_bps * 2.0)
        gross_edge = _edge_from_signal(signal)
        edge_context = {
            "expected_move_bps": gross_edge,
            "spread_bps": spread_bps,
            "total_cost_bps": cost_bps,
            "net_edge_bps": gross_edge - cost_bps,
            "adaptive_min_edge_bps": self.config.opportunity_config.min_net_edge_bps,
        }
        result = self.scorer.score_signal(
            symbol=signal.symbol,
            edge_context=edge_context,
            atr_pct=_safe_float(signal.metadata.get("atr_pct"), 0.01),
            available_capital=ledger.portfolio.cash_eur,
            open_positions=len(ledger.portfolio.positions),
            market_metrics=None,
            total_capital=ledger.portfolio.equity_eur,
            paper_mode=True,
            price_history=price_history,
            performance_context={"status": "unknown", "closed_trades": 0, "health_score": 50.0, "adjustment": 0.0},
        )
        return OpportunityScoreEvent(signal=signal, result=result)

    def _order_from_risk(self, risk: RiskDecision, event: MarketEvent) -> SimulatedOrder:
        signal = risk.signal
        quantity = risk.quantity
        if signal.side == "sell" and quantity <= 0:
            quantity = 0.0
        self._order_seq += 1
        return SimulatedOrder(
            order_id=f"{self.config.run_id}-order-{self._order_seq}",
            run_id=self.config.run_id,
            strategy_id=self.config.strategy_id,
            symbol=signal.symbol,
            side=signal.side,
            order_type=signal.order_type,
            requested_price=signal.price,
            requested_quantity=quantity,
            notional_eur=risk.order_notional_eur or (quantity * event.price),
            timestamp=event.timestamp,
            limit_price=signal.limit_price,
            reason=signal.reason,
            metadata={"signal_reason": signal.reason},
        )

    def _spread_bps(self, event: MarketEvent) -> float:
        if event.bid and event.ask and event.bid > 0 and event.ask >= event.bid:
            mid = (event.ask + event.bid) / 2.0
            return (event.ask - event.bid) / mid * 10_000.0
        return self.config.execution_config.spread_bps

    def _decide(self, metrics: StrategyMetrics, baselines: Sequence[BaselineResult]) -> HarnessValidationDecision:
        no_trade = next((base for base in baselines if base.name == "no_trade_baseline"), None)
        buy_hold = next((base for base in baselines if base.name == "buy_and_hold"), None)
        best_baseline = max(baselines, key=lambda item: item.net_pnl_eur) if baselines else None
        criteria = self.config.acceptance_criteria
        pf_ok = metrics.profit_factor is not None and metrics.profit_factor >= criteria.min_profit_factor
        checks = {
            "live_promotion_allowed": False,
            "closed_trades": metrics.trade_count,
            "min_closed_trades": criteria.min_closed_trades,
            "profit_factor": metrics.profit_factor,
            "min_profit_factor": criteria.min_profit_factor,
            "net_pnl_eur": metrics.final_equity_eur - metrics.initial_capital_eur,
            "max_drawdown_pct": metrics.max_drawdown_pct,
            "baseline_comparison": best_baseline.name if best_baseline else None,
            "baseline_delta_eur": (metrics.final_equity_eur - metrics.initial_capital_eur) - (best_baseline.net_pnl_eur if best_baseline else 0.0),
            "no_trade_delta_eur": (metrics.final_equity_eur - metrics.initial_capital_eur) - (no_trade.net_pnl_eur if no_trade else 0.0),
            "buy_and_hold_delta_eur": (metrics.final_equity_eur - metrics.initial_capital_eur) - (buy_hold.net_pnl_eur if buy_hold else 0.0),
        }
        if metrics.trade_count < criteria.min_closed_trades:
            return HarnessValidationDecision(
                status="keep_testing",
                reason="insufficient_closed_trades",
                recommended_registry_status="candidate",
                live_promotion_allowed=False,
                checks=checks,
            )
        if metrics.final_equity_eur <= metrics.initial_capital_eur:
            return HarnessValidationDecision(
                status="modify",
                reason="net_pnl_not_positive",
                recommended_registry_status="candidate",
                live_promotion_allowed=False,
                checks=checks,
            )
        if not pf_ok:
            return HarnessValidationDecision(
                status="modify",
                reason="profit_factor_below_threshold",
                recommended_registry_status="candidate",
                live_promotion_allowed=False,
                checks=checks,
            )
        if best_baseline and checks["baseline_delta_eur"] <= criteria.min_baseline_delta_eur:
            return HarnessValidationDecision(
                status="modify",
                reason="does_not_beat_best_baseline",
                recommended_registry_status="candidate",
                live_promotion_allowed=False,
                checks=checks,
            )
        return HarnessValidationDecision(
            status="promote_candidate",
            reason="passes_replay_gate_for_human_review_only",
            recommended_registry_status="backtest_passed",
            live_promotion_allowed=False,
            checks=checks,
        )

    def _registry_proposal(self, decision: HarnessValidationDecision, metrics: StrategyMetrics) -> dict[str, Any]:
        return {
            "strategy_id": self.config.strategy_id,
            "proposed_validation_status": decision.recommended_registry_status,
            "last_backtest_id": self.config.run_id,
            "decision": decision.status,
            "decision_reason": decision.reason,
            "live_auto_promotion_allowed": False,
            "metrics_summary": {
                "closed_trades": metrics.trade_count,
                "net_return_pct": metrics.total_return_net_pct,
                "profit_factor": _finite_or_none(metrics.profit_factor),
                "max_drawdown_pct": metrics.max_drawdown_pct,
            },
        }

    def write_report(self, result: ValidationRunResult) -> Path:
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.config.output_dir / f"{result.run_id}.md"
        path.write_text(render_validation_report(result), encoding="utf-8")
        return path


def render_validation_report(result: ValidationRunResult) -> str:
    metrics = result.metrics
    lines = [
        f"# Validation Run - {result.run_id}",
        "",
        f"Strategy: `{result.strategy_id}`",
        f"Symbol: `{result.symbol}`",
        f"Dataset: `{result.dataset_id}`",
        f"Period: `{result.started_at.isoformat()}` to `{result.ended_at.isoformat()}`",
        f"Market events replayed: `{result.market_event_count}`",
        "",
        "## Hypothesis",
        "",
        result.hypothesis,
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Initial capital | {metrics.initial_capital_eur:.2f} |",
        f"| Final equity | {metrics.final_equity_eur:.2f} |",
        f"| Realized gross PnL | {metrics.realized_gross_pnl_eur:.6f} |",
        f"| Realized net PnL | {metrics.realized_net_pnl_eur:.6f} |",
        f"| Total net PnL | {metrics.total_net_pnl_eur:.6f} |",
        f"| Total return gross | {metrics.total_return_gross_pct:.4f}% |",
        f"| Total return net | {metrics.total_return_net_pct:.4f}% |",
        f"| Max drawdown | {metrics.max_drawdown_pct:.4f}% |",
        f"| Profit factor | {_format_optional(metrics.profit_factor)} |",
        f"| Winrate | {metrics.winrate_pct:.2f}% |",
        f"| Expectancy | {metrics.expectancy_eur:.6f} |",
        f"| Closed trades | {metrics.trade_count} |",
        f"| Average win | {metrics.average_win_eur:.6f} |",
        f"| Average loss | {metrics.average_loss_eur:.6f} |",
        f"| Average duration seconds | {_format_optional(metrics.average_trade_duration_seconds)} |",
        f"| Sharpe | {_format_optional(metrics.sharpe)} |",
        f"| Sortino | {_format_optional(metrics.sortino)} |",
        f"| Fees total | {metrics.total_fees_eur:.6f} |",
        f"| Slippage total | {metrics.total_slippage_eur:.6f} |",
        "",
        "## Baselines",
        "",
        "| Baseline | Net PnL | Net return | Trades | Profit factor | Max DD |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for baseline in result.baselines:
        lines.append(
            f"| {baseline.name} | {baseline.net_pnl_eur:.6f} | {baseline.total_return_net_pct:.4f}% | "
            f"{baseline.trade_count} | {_format_optional(baseline.profit_factor)} | {baseline.max_drawdown_pct:.4f}% |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"Recommended status: `{result.decision.status}`",
            f"Registry proposal: `{result.decision.recommended_registry_status}`",
            f"Reason: `{result.decision.reason}`",
            f"Live promotion allowed: `{result.decision.live_promotion_allowed}`",
            "",
            "## Replay Ledger",
            "",
            f"Signals generated: {result.signal_count}",
            f"Simulated orders: {result.simulated_order_count}",
            f"Fills: {result.fill_count}",
            f"Ledger entries: {len(result.ledger)}",
            f"Rejected signals: {len(result.rejected_signals)}",
            "",
            "## Registry Update Proposal",
            "",
            "```json",
            json.dumps(result.registry_update_proposal, indent=2),
            "```",
            "",
            "## Conclusion",
            "",
            _conclusion_text(result),
            "",
        ]
    )
    return "\n".join(lines)


def _edge_from_signal(signal: SignalEvent) -> float:
    metadata = signal.metadata or {}
    for key in ("expected_move_bps", "gross_edge_bps", "edge_bps"):
        if key in metadata:
            return _safe_float(metadata.get(key), 0.0)
    if "diff_pct" in metadata:
        return abs(_safe_float(metadata.get("diff_pct"), 0.0)) * 100.0
    if "trend_strength_pct" in metadata:
        return abs(_safe_float(metadata.get("trend_strength_pct"), 0.0)) * 100.0
    return 0.0


def _optional_positive(value: Any) -> float | None:
    result = _safe_float(value, 0.0)
    return result if result > 0.0 else None


def _sharpe(returns: Sequence[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    std = math.sqrt(max(variance, 0.0))
    return None if std <= 0 else mean / std * math.sqrt(len(returns))


def _sortino(returns: Sequence[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    downside = [min(0.0, value) for value in returns]
    downside_variance = sum(value * value for value in downside) / len(returns)
    downside_std = math.sqrt(max(downside_variance, 0.0))
    return None if downside_std <= 0 else mean / downside_std * math.sqrt(len(returns))


def _by_regime(closing_entries: Sequence[LedgerEntry]) -> dict[str, dict[str, float]]:
    groups: dict[str, list[float]] = {}
    for entry in closing_entries:
        regime = str(entry.metadata.get("regime") or "unknown")
        groups.setdefault(regime, []).append(entry.net_pnl_eur)
    return {
        regime: {
            "trade_count": float(len(values)),
            "net_pnl_eur": sum(values),
            "winrate_pct": (sum(1 for value in values if value > 0) / len(values) * 100.0) if values else 0.0,
        }
        for regime, values in groups.items()
    }


def _format_optional(value: float | None) -> str:
    if value is None:
        return "N/A"
    if math.isinf(value):
        return "inf"
    return f"{value:.6f}"


def _finite_or_none(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return value


def _conclusion_text(result: ValidationRunResult) -> str:
    if result.decision.status == "promote_candidate":
        return "The replay passes the research gate for human review only. It does not authorize live trading."
    if result.decision.status == "keep_testing":
        return "The sample is not large enough. Continue replay/paper validation before any promotion."
    if result.decision.status == "modify":
        return "The strategy did not meet objective replay criteria. Modify or continue diagnostics before promotion."
    return "The strategy should remain blocked from promotion."


def load_events_from_rows(rows: Iterable[Mapping[str, Any]], *, default_symbol: str | None = None) -> list[MarketEvent]:
    return [MarketEvent.from_mapping(row, default_symbol=default_symbol) for row in rows]


def _connect_sqlite_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _merge_symbols(symbol: str | None, symbols: Sequence[str] | None) -> list[str]:
    values: list[str] = []
    if symbol:
        values.append(symbol)
    if symbols:
        values.extend(symbols)
    return [str(value).upper() for value in values if str(value or "").strip()]


def _sqlite_filters(
    *,
    symbol_column: str | None,
    time_column: str | None,
    symbols: Sequence[str],
    start_at: Any | None,
    end_at: Any | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    args: list[Any] = []
    if symbol_column and symbols:
        placeholders = ",".join("?" for _ in symbols)
        clauses.append(f"{symbol_column} IN ({placeholders})")
        args.extend(symbols)
    if time_column and start_at is not None:
        clauses.append(f"{time_column} >= ?")
        args.append(_parse_timestamp(start_at).isoformat())
    if time_column and end_at is not None:
        clauses.append(f"{time_column} <= ?")
        args.append(_parse_timestamp(end_at).isoformat())
    return (f"WHERE {' AND '.join(clauses)}" if clauses else "", args)


def _row_get(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    return row[key] if key in row.keys() else default


def _first_positive(row: sqlite3.Row, keys: Sequence[str]) -> float:
    for key in keys:
        value = _safe_float(_row_get(row, key), 0.0)
        if value > 0.0:
            return value
    return 0.0


def _include_ledger_leg(row: sqlite3.Row, *, include_opening: bool, include_closing: bool) -> bool:
    opening = _row_get(row, "is_opening_leg")
    closing = _row_get(row, "is_closing_leg")
    if opening is None and closing is None:
        return True
    if bool(opening) and not include_opening:
        return False
    if bool(closing) and not include_closing:
        return False
    return True
