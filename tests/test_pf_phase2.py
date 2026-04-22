from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from autobot.v2.persistence import StatePersistence
from autobot.v2.pf_validation import apply_cost_sensitivity, walk_forward_validate
from autobot.v2.signal_handler_async import SignalHandlerAsync
from autobot.v2.strategies import SignalType, TradingSignal


def test_trade_ledger_metrics_profit_factor_expectancy(tmp_path):
    db = tmp_path / "state.db"
    p = StatePersistence(str(db))
    p.append_trade_ledger(
        trade_id="t1",
        instance_id="i1",
        symbol="XXBTZEUR",
        side="sell",
        executed_price=101.0,
        volume=1.0,
        fees=0.2,
        realized_pnl=10.0,
        is_closing_leg=True,
    )
    p.append_trade_ledger(
        trade_id="t2",
        instance_id="i1",
        symbol="XXBTZEUR",
        side="sell",
        executed_price=99.0,
        volume=1.0,
        fees=0.2,
        realized_pnl=-5.0,
        is_closing_leg=True,
    )
    metrics = p.get_trade_ledger_metrics("i1")
    assert metrics["trade_count"] == 2.0
    assert metrics["profit_factor"] == 2.0
    assert metrics["expectancy"] == 2.5
    assert metrics["total_fees"] == 0.4


@dataclass
class _DummyConfig:
    max_positions: int = 10


@dataclass
class _DummyInstance:
    id: str = "inst"
    config: _DummyConfig = field(default_factory=_DummyConfig)
    _strategy: object = None
    _price_history: deque = field(
        default_factory=lambda: deque(
            [(datetime.now(timezone.utc), p) for p in (100.0, 101.0, 99.5, 100.5, 102.0)],
            maxlen=200,
        )
    )
    _last_price: float = 102.0

    def get_positions_snapshot(self):
        return [{"status": "open", "buy_price": 100.0, "volume": 0.5}]

    def get_current_capital(self):
        return 1000.0

    def get_profit(self):
        return 10.0


class _DummyPersistence:
    def __init__(self, total_fees: float | None):
        self.total_fees = total_fees

    def get_trade_ledger_metrics(self, _instance_id):
        return {"total_fees": self.total_fees}


class _DummyExecutor:
    def __init__(self, balance_zeur=1000.0, trade_balance=None):
        self._balance_zeur = balance_zeur
        self._trade_balance = trade_balance or {}

    async def get_balance(self):
        return {"ZEUR": self._balance_zeur}

    async def get_trade_balance(self, _asset):
        return self._trade_balance


class _DummyKillSwitch:
    def __init__(self):
        self.triggers = []
        self.freshness_events = []

    def record_balance_freshness(self, ts):
        self.freshness_events.append(ts)

    async def trigger(self, reason, message):
        self.triggers.append((reason, message))


def test_cost_guard_filters_low_edge_signal():
    h = SignalHandlerAsync(instance=_DummyInstance(), order_executor=None)
    h._max_spread_bps = 30.0
    h._tp_rr = 1.5
    h._min_edge_bps = 15.0
    sig = TradingSignal(
        type=SignalType.BUY,
        symbol="BTC/EUR",
        price=100.0,
        volume=0.0,
        reason="test",
        timestamp=datetime.now(timezone.utc),
        metadata={"spread_bps": 50.0, "expected_move_bps": 55.0, "fee_bps": 40.0, "slippage_bps": 10.0},
    )
    assert h._passes_cost_guard(sig, atr_pct=0.01) is False


def test_walk_forward_and_cost_sensitivity_low_compute():
    pnls = [2.0, -1.0, 1.5, -0.5, 2.2, -0.8] * 40
    stressed = apply_cost_sensitivity(pnls, fee_slippage_penalty_per_trade=0.2)
    wf = walk_forward_validate(stressed, train_size=80, test_size=40, step=40, min_test_trades=20)
    assert wf
    assert all(s.trade_count >= 20 for s in wf)


@pytest.mark.asyncio
async def test_post_trade_reconcile_aligned_metrics(caplog):
    instance = _DummyInstance()
    instance._persistence = _DummyPersistence(total_fees=1.5)
    executor = _DummyExecutor(
        balance_zeur=1000.0,
        trade_balance={"n": 10.0, "u": 1.0, "c": 1.5},
    )
    handler = SignalHandlerAsync(instance=instance, order_executor=executor)
    handler._kill_switch = _DummyKillSwitch()

    with caplog.at_level("INFO"):
        await handler._post_trade_reconcile()

    assert handler._kill_switch.triggers == []
    assert "qualité=complet" in caplog.text


@pytest.mark.asyncio
async def test_post_trade_reconcile_detects_real_divergence():
    instance = _DummyInstance()
    instance._persistence = _DummyPersistence(total_fees=8.0)
    executor = _DummyExecutor(
        balance_zeur=900.0,  # strong cash drift
        trade_balance={"n": -20.0, "u": 0.0, "c": 0.1},
    )
    handler = SignalHandlerAsync(instance=instance, order_executor=executor)
    handler._kill_switch = _DummyKillSwitch()

    await handler._post_trade_reconcile()

    assert handler._kill_switch.triggers
    assert handler._kill_switch.triggers[0][0] == "reconciliation_mismatch"


@pytest.mark.asyncio
async def test_post_trade_reconcile_partial_local_data_logs_incomplete(caplog):
    instance = _DummyInstance()
    instance._last_price = None
    instance._persistence = _DummyPersistence(total_fees=None)
    executor = _DummyExecutor(
        balance_zeur=1000.0,
        trade_balance={"n": 10.0, "u": 0.0, "c": 1.0},
    )
    handler = SignalHandlerAsync(instance=instance, order_executor=executor)
    handler._kill_switch = _DummyKillSwitch()

    with caplog.at_level("INFO"):
        await handler._post_trade_reconcile()

    assert "qualité=incomplet" in caplog.text
