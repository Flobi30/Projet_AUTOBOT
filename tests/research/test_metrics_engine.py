from datetime import datetime, timezone

import pytest

from autobot.v2.research.metrics_engine import MetricsEngine
from autobot.v2.research.trade_journal import TradeRecord


pytestmark = pytest.mark.unit


def _trade(pnl, minute, regime="range"):
    return TradeRecord(
        run_id="run-1",
        strategy_id="grid_core",
        symbol="TRXEUR",
        side="buy",
        opened_at=datetime(2026, 5, 31, 0, minute - 1, tzinfo=timezone.utc),
        closed_at=datetime(2026, 5, 31, 0, minute, tzinfo=timezone.utc),
        quantity=10.0,
        entry_price=1.0,
        exit_price=1.1,
        gross_pnl_eur=pnl + 0.1,
        net_pnl_eur=pnl,
        fees_eur=0.1,
        slippage_eur=0.02,
        spread_cost_eur=0.03,
        latency_cost_eur=0.01,
        regime=regime,
    )


def test_metrics_engine_calculates_net_metrics_and_baseline_delta():
    trades = [_trade(2.0, 1), _trade(-1.0, 2), _trade(3.0, 3, regime="trend")]

    metrics = MetricsEngine().calculate(
        trades,
        initial_capital_eur=100.0,
        baseline_name="buy_and_hold",
        baseline_return_pct=1.0,
    )

    assert metrics.trade_count == 3
    assert metrics.total_net_pnl_eur == 4.0
    assert metrics.total_return_pct == 4.0
    assert round(metrics.winrate_pct or 0.0, 2) == 66.67
    assert metrics.profit_factor == 5.0
    assert round(metrics.expectancy_eur or 0.0, 4) == 1.3333
    assert metrics.max_drawdown_eur == 1.0
    assert metrics.baseline_delta_pct == 3.0
    assert metrics.beats_baseline is True
    assert metrics.performance_by_regime["range"]["trade_count"] == 2
    assert metrics.performance_by_regime["trend"]["net_pnl_eur"] == 3.0


def test_metrics_engine_returns_none_for_undefined_profit_factor():
    metrics = MetricsEngine().calculate([_trade(1.0, 1), _trade(2.0, 2)], initial_capital_eur=100.0)

    assert metrics.profit_factor is None
    assert metrics.winrate_pct == 100.0


def test_metrics_engine_handles_empty_trade_set_without_fake_performance():
    metrics = MetricsEngine().calculate([], initial_capital_eur=100.0, baseline_name="no_trade", baseline_return_pct=0.0)

    assert metrics.trade_count == 0
    assert metrics.total_net_pnl_eur == 0
    assert metrics.winrate_pct is None
    assert metrics.profit_factor is None
    assert metrics.beats_baseline is False
