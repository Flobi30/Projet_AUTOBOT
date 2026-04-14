from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

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


def test_cost_guard_filters_low_edge_signal():
    h = SignalHandlerAsync(instance=_DummyInstance(), order_executor=None)
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
