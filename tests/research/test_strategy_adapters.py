from datetime import datetime, timezone

import pytest

from autobot.v2.research.market_data_repository import MarketBar
from autobot.v2.research.strategy_adapters import RuntimeStrategyBacktestAdapter, TradingSignalAdapter
from autobot.v2.strategies import SignalType, Strategy, TradingSignal


pytestmark = pytest.mark.unit


def _signal(signal_type, volume=0.0):
    return TradingSignal(
        type=signal_type,
        symbol="TRXEUR",
        price=1.23,
        volume=volume,
        reason="pytest",
        timestamp=datetime(2026, 5, 31, tzinfo=timezone.utc),
        metadata={"gross_edge_bps": 42.0},
    )


def test_trading_signal_adapter_converts_buy_sell_close_and_ignores_hold():
    buy = TradingSignalAdapter.to_backtest_signal(_signal(SignalType.BUY), default_notional_eur=25.0, strategy_id="demo")
    sell = TradingSignalAdapter.to_backtest_signal(_signal(SignalType.SELL, volume=10.0))
    close = TradingSignalAdapter.to_backtest_signal(_signal(SignalType.CLOSE, volume=-1.0))
    hold = TradingSignalAdapter.to_backtest_signal(_signal(SignalType.HOLD))

    assert buy is not None
    assert buy.side == "buy"
    assert buy.notional_eur == 25.0
    assert buy.metadata["strategy_id"] == "demo"
    assert sell is not None
    assert sell.side == "sell"
    assert sell.quantity == 10.0
    assert close is not None
    assert close.side == "sell"
    assert close.metadata["close_all"] is True
    assert hold is None


class ToyStrategy(Strategy):
    def on_price(self, price: float):
        self.emit_signal(
            TradingSignal(
                type=SignalType.BUY,
                symbol=self.instance.config.symbol,
                price=price,
                volume=0.0,
                reason="toy_buy",
                timestamp=datetime(2026, 5, 31, tzinfo=timezone.utc),
                metadata={"gross_edge_bps": 12.0},
            )
        )

    def on_position_opened(self, position):
        return None

    def on_position_closed(self, position, profit: float):
        return None


def test_runtime_strategy_backtest_adapter_collects_runtime_signals():
    adapter = RuntimeStrategyBacktestAdapter(
        lambda instance, config: ToyStrategy(instance, config),
        symbol="TRXEUR",
        strategy_id="toy_strategy",
        default_notional_eur=50.0,
    )
    bar = MarketBar(
        timestamp=datetime(2026, 5, 31, tzinfo=timezone.utc),
        symbol="TRXEUR",
        timeframe="1m",
        open=1.0,
        high=1.3,
        low=0.9,
        close=1.2,
        volume=100.0,
    )

    signals = list(adapter(bar, [bar]))

    assert len(signals) == 1
    assert signals[0].side == "buy"
    assert signals[0].price == 1.2
    assert signals[0].notional_eur == 50.0
    assert signals[0].metadata["strategy_id"] == "toy_strategy"
