from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from autobot.v2.order_executor import OrderResult
from autobot.v2.signal_handler_async import SignalHandlerAsync
from autobot.v2.strategies import SignalType, TradingSignal
from autobot.v2.validator import ValidationStatus


pytestmark = pytest.mark.unit


@dataclass
class _Config:
    max_positions: int = 5
    atr_sl_mult: float = 2.2
    tp_rr: float = 1.9
    fallback_atr_pct: float = 0.02
    max_spread_bps: float = 25.0
    min_edge_bps: float = 9.0
    risk_per_trade_pct: float = 1.5
    max_position_capital_pct: float = 20.0


class _Instance:
    def __init__(self):
        self.id = "inst-unit"
        self.config = _Config()
        self.status = SimpleNamespace(value="running")
        self._strategy = None
        self._price_history = []
        self._last_price = 100.0
        self._persistence = SimpleNamespace(append_audit_event=lambda **_: None)
        self.opened = []

    def get_available_capital(self):
        return 1_000.0

    def get_positions_snapshot(self):
        return []

    async def open_position(self, **kwargs):
        self.opened.append(kwargs)
        return SimpleNamespace(id="pos-1")

    def get_current_capital(self):
        return 1_000.0

    def get_profit(self):
        return 0.0

    async def emergency_stop(self):
        return None


class _Validator:
    def validate(self, *_args, **_kwargs):
        return SimpleNamespace(status=ValidationStatus.GREEN, message="ok")


class _OSM:
    def is_duplicate_active(self, *_args, **_kwargs):
        return False

    def new_order(self, **_kwargs):
        return SimpleNamespace(client_order_id="cid-1")

    def transition(self, *_args, **_kwargs):
        return None


class _CountingOSM(_OSM):
    def __init__(self):
        self.new_order_calls = 0

    def new_order(self, **_kwargs):
        self.new_order_calls += 1
        return super().new_order(**_kwargs)


class _Executor:
    def __init__(self):
        self.market_calls = 0
        self.limit_calls = 0

    async def execute_market_order(self, *_args, **_kwargs):
        self.market_calls += 1
        return OrderResult(success=True, txid="buy-1", executed_volume=0.2, executed_price=100.0)

    async def execute_limit_order(self, *_args, **_kwargs):
        self.limit_calls += 1
        return OrderResult(success=True, txid="buy-1", executed_volume=0.2, executed_price=100.0)

    async def execute_stop_loss_order(self, *_args, **_kwargs):
        return OrderResult(success=True, txid="sl-1")


@pytest.mark.asyncio
async def test_execute_buy_and_cost_guard_without_external_injection():
    handler = SignalHandlerAsync(instance=_Instance(), order_executor=_Executor())
    handler.validator = _Validator()
    handler._osm = _OSM()
    handler._post_trade_reconcile = _noop_reconcile

    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=100.0,
        volume=0.2,
        reason="unit",
        timestamp=datetime.now(timezone.utc),
        metadata={"spread_bps": 10.0, "expected_move_bps": 120.0, "fee_bps": 20.0, "slippage_bps": 8.0},
    )

    assert handler._passes_cost_guard(signal, atr_pct=0.01) is True

    await handler._execute_buy(signal)

    assert len(handler.instance.opened) == 1
    assert handler.instance.opened[0]["buy_txid"] == "buy-1"


@pytest.mark.asyncio
async def test_execute_buy_blocks_order_below_minimum_before_executor():
    executor = _Executor()
    osm = _CountingOSM()
    handler = SignalHandlerAsync(instance=_Instance(), order_executor=executor)
    handler.validator = _Validator()
    handler._osm = osm
    handler._post_trade_reconcile = _noop_reconcile
    handler._opportunity_gate_applies = lambda: {"selection_applies_to_execution": False}

    signal = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=65_000.0,
        volume=0.000044,
        reason="unit below min",
        timestamp=datetime.now(timezone.utc),
        metadata={"spread_bps": 1.0, "expected_move_bps": 200.0, "fee_bps": 10.0, "slippage_bps": 2.0},
    )

    await handler._execute_buy(signal)

    assert osm.new_order_calls == 0
    assert executor.market_calls == 0
    assert executor.limit_calls == 0
    assert handler.instance.opened == []
    assert handler._last_decision_event["reason"] == "order_size_below_minimum"
    assert handler._last_decision_event["min_volume"] == 0.0001


def test_init_loads_env_and_clamps_invalid_ranges():
    import os

    env_backup = {k: os.environ.get(k) for k in ("ATR_SL_MULT", "TP_RR", "FALLBACK_ATR_PCT", "MAX_SPREAD_BPS", "MIN_EDGE_BPS")}
    try:
        os.environ["ATR_SL_MULT"] = "-4"  # invalid -> fallback then clamp
        os.environ["TP_RR"] = "0"  # invalid -> fallback
        os.environ["FALLBACK_ATR_PCT"] = "10"  # valid but clamped to safe range
        os.environ["MAX_SPREAD_BPS"] = "0"  # invalid -> fallback
        os.environ["MIN_EDGE_BPS"] = "20000"  # clamped

        handler = SignalHandlerAsync(instance=_Instance(), order_executor=None)

        assert handler._atr_sl_mult > 0
        assert handler._tp_rr > 0
        assert 0.001 <= handler._fallback_atr_pct <= 0.25
        assert 1.0 <= handler._max_spread_bps <= 1000.0
        assert 1.0 <= handler._min_edge_bps <= 1000.0
    finally:
        for key, value in env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


async def _noop_reconcile():
    return None
