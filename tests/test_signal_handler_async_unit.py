from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from autobot.v2.order_executor import OrderResult
from autobot.v2.signal_handler_async import SignalHandlerAsync
from autobot.v2.strategies import SignalType, TradingSignal

pytestmark = pytest.mark.unit


@dataclass
class _Cfg:
    max_positions: int = 5


class _Instance:
    def __init__(self) -> None:
        self.id = "inst-unit"
        self.config = _Cfg()
        self._strategy = None
        self.status = SimpleNamespace(value="running")
        self._price_history = []
        self._persistence = SimpleNamespace(append_audit_event=lambda **_: None)

    def get_available_capital(self):
        return 1_000.0

    def get_positions_snapshot(self):
        return []

    async def open_position(self, **_kwargs):
        return None


class _Executor:
    def __init__(self) -> None:
        self.market_calls = []

    async def execute_market_order(self, symbol, side, volume):
        self.market_calls.append((symbol, side.value, volume))
        return OrderResult(success=True, txid="tx_buy", executed_volume=volume, executed_price=100.0, fees=0.2)

    async def execute_stop_loss_order(self, symbol, side, volume, stop_price):
        return OrderResult(success=True, txid="tx_sl", executed_volume=volume, executed_price=stop_price)


@pytest.mark.asyncio
async def test_execute_buy_uses_safe_defaults_without_injection(monkeypatch):
    monkeypatch.delenv("ATR_SL_MULT", raising=False)
    monkeypatch.delenv("TP_RR", raising=False)
    monkeypatch.delenv("FALLBACK_ATR_PCT", raising=False)
    monkeypatch.delenv("MAX_SPREAD_BPS", raising=False)
    monkeypatch.delenv("MIN_EDGE_BPS", raising=False)

    instance = _Instance()
    executor = _Executor()
    handler = SignalHandlerAsync(instance=instance, order_executor=executor)

    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=100.0,
        volume=0.0,
        reason="unit-buy",
        timestamp=datetime.now(timezone.utc),
        metadata={"spread_bps": 5.0, "expected_move_bps": 80.0, "fee_bps": 20.0, "slippage_bps": 6.0},
    )

    await handler._execute_buy(signal)

    assert executor.market_calls, "_execute_buy should place a market order with internal defaults"


def test_passes_cost_guard_works_with_env_and_bounds(monkeypatch):
    monkeypatch.setenv("MAX_SPREAD_BPS", "40")
    monkeypatch.setenv("MIN_EDGE_BPS", "10")
    monkeypatch.setenv("TP_RR", "1.7")

    handler = SignalHandlerAsync(instance=_Instance(), order_executor=None)

    ok_signal = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=100.0,
        volume=0.0,
        reason="ok",
        timestamp=datetime.now(timezone.utc),
        metadata={"spread_bps": 8.0, "expected_move_bps": 95.0, "fee_bps": 25.0, "slippage_bps": 6.0},
    )
    bad_signal = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=100.0,
        volume=0.0,
        reason="bad",
        timestamp=datetime.now(timezone.utc),
        metadata={"spread_bps": 55.0, "expected_move_bps": 70.0, "fee_bps": 25.0, "slippage_bps": 10.0},
    )

    assert handler._passes_cost_guard(ok_signal, atr_pct=0.01) is True
    assert handler._passes_cost_guard(bad_signal, atr_pct=0.01) is False
