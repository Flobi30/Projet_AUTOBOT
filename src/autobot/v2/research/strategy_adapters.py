"""Adapters between runtime AUTOBOT strategies and research backtests."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Sequence

from autobot.v2.strategies import SignalType, Strategy, TradingSignal

from .backtest_engine import BacktestSignal
from .market_data_repository import MarketBar


@dataclass
class ResearchStrategyInstance:
    """Minimal fake instance for runtime strategy adapters.

    It exposes only the methods used by legacy synchronous strategies. This is
    research-only and must not be confused with a live/paper TradingInstance.
    """

    symbol: str
    available_capital_eur: float = 1_000.0
    positions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.config = SimpleNamespace(symbol=self.symbol)

    def get_available_capital(self) -> float:
        return float(self.available_capital_eur)

    def get_current_capital(self) -> float:
        return float(self.available_capital_eur)

    def get_positions_snapshot(self) -> dict[str, dict[str, Any]]:
        return dict(self.positions)


class TradingSignalAdapter:
    """Convert AUTOBOT runtime `TradingSignal` objects to research signals."""

    @staticmethod
    def to_backtest_signal(
        signal: TradingSignal,
        *,
        default_notional_eur: float | None = None,
        strategy_id: str | None = None,
    ) -> BacktestSignal | None:
        if signal.type == SignalType.HOLD:
            return None
        side = "buy" if signal.type == SignalType.BUY else "sell"
        quantity = float(signal.volume) if float(signal.volume) > 0.0 else None
        metadata = dict(signal.metadata or {})
        if signal.type == SignalType.CLOSE:
            metadata.setdefault("close_all", True)
        if strategy_id:
            metadata.setdefault("strategy_id", strategy_id)
        return BacktestSignal(
            symbol=signal.symbol,
            side=side,
            price=float(signal.price),
            timestamp=signal.timestamp,
            reason=signal.reason,
            quantity=quantity,
            notional_eur=default_notional_eur if quantity is None and side == "buy" else None,
            order_type=str(metadata.get("order_type") or "market"),
            limit_price=metadata.get("limit_price"),
            metadata=metadata,
        )


class RuntimeStrategyBacktestAdapter:
    """Wrap a synchronous runtime Strategy as a BacktestEngine signal generator.

    The adapter only translates signals. It does not update official runtime
    positions, does not execute orders, and does not touch live/paper state.
    """

    def __init__(
        self,
        strategy_factory: Callable[[ResearchStrategyInstance, dict[str, Any]], Strategy],
        *,
        symbol: str,
        strategy_id: str,
        config: dict[str, Any] | None = None,
        initial_capital_eur: float = 1_000.0,
        default_notional_eur: float | None = None,
    ) -> None:
        self.strategy_id = strategy_id
        self.default_notional_eur = default_notional_eur
        self.instance = ResearchStrategyInstance(symbol=symbol, available_capital_eur=initial_capital_eur)
        self.strategy = strategy_factory(self.instance, dict(config or {}))
        self._pending_signals: list[TradingSignal] = []
        self.strategy.set_signal_callback(self._pending_signals.append)

    def __call__(self, bar: MarketBar, _history: Sequence[MarketBar]) -> Iterable[BacktestSignal]:
        self._pending_signals.clear()
        self.strategy.safe_on_price(bar.close)
        converted: list[BacktestSignal] = []
        for signal in self._pending_signals:
            backtest_signal = TradingSignalAdapter.to_backtest_signal(
                signal,
                default_notional_eur=self.default_notional_eur,
                strategy_id=self.strategy_id,
            )
            if backtest_signal is not None:
                converted.append(backtest_signal)
        return converted
