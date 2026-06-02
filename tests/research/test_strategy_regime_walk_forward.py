from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.market_data_repository import MarketBar
from autobot.v2.research.strategy_regime_walk_forward import (
    evaluate_strategy_regime_walk_forward,
    render_strategy_regime_walk_forward_report,
    write_strategy_regime_walk_forward_report,
)
from autobot.v2.research.trade_journal import TradeRecord


pytestmark = pytest.mark.unit


def _bar(index, close, *, regime="range"):
    timestamp = datetime(2026, 6, 2, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=index)
    return MarketBar(
        timestamp=timestamp,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1_000.0,
        symbol="TRXEUR",
        timeframe="1m",
        metadata={"regime": regime},
    )


def _trade(index, net, *, regime="range"):
    opened_at = datetime(2026, 6, 2, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=index - 1)
    closed_at = datetime(2026, 6, 2, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=index)
    return TradeRecord(
        run_id="pytest_regime_wf",
        strategy_id="dynamic_grid",
        symbol="TRXEUR",
        side="long",
        opened_at=opened_at,
        closed_at=closed_at,
        quantity=1.0,
        entry_price=100.0,
        exit_price=101.0,
        gross_pnl_eur=net,
        net_pnl_eur=net,
        regime=regime,
        metadata={"entry": {"strategy_id": "dynamic_grid", "regime": regime}},
    )


def test_strategy_regime_walk_forward_counts_baseline_passing_folds(tmp_path):
    bars = [
        _bar(0, 100.0),
        _bar(1, 100.0),
        _bar(2, 101.0),
        _bar(3, 101.0),
        _bar(4, 101.0),
        _bar(5, 100.0),
    ]
    report = evaluate_strategy_regime_walk_forward(
        [_trade(2, 2.0), _trade(4, -1.0)],
        bars,
        run_id="pytest_regime_wf",
        train_window_bars=1,
        test_window_bars=2,
        step_window_bars=2,
        min_folds=2,
        min_passing_folds=2,
        min_total_trades=1,
        initial_capital_eur=100.0,
        order_notional_eur=10.0,
        cost_config=ExecutionCostConfig(taker_fee_bps=0.0, fallback_spread_bps=0.0, slippage_bps=0.0),
    )

    summary = report.summaries[0]

    assert report.fold_count == 2
    assert report.evaluated_bucket_count == 2
    assert summary.evaluated_fold_count == 2
    assert summary.passing_fold_count == 1
    assert summary.positive_fold_count == 1
    assert summary.status == "modify"
    assert summary.reason == "insufficient_baseline_passing_folds"

    written = write_strategy_regime_walk_forward_report(report, tmp_path)
    markdown = render_strategy_regime_walk_forward_report(written)

    assert written.json_report_path
    assert written.markdown_report_path
    assert "Strategy Regime Walk-Forward Report" in markdown
    assert "research-only" in markdown


def test_strategy_regime_walk_forward_keeps_tiny_samples_in_learning():
    bars = [_bar(index, 100.0) for index in range(6)]
    report = evaluate_strategy_regime_walk_forward(
        [_trade(2, 2.0), _trade(4, 2.0)],
        bars,
        run_id="pytest_tiny_sample",
        train_window_bars=1,
        test_window_bars=2,
        step_window_bars=2,
        min_folds=2,
        min_passing_folds=2,
        min_total_trades=30,
        initial_capital_eur=100.0,
        order_notional_eur=10.0,
        cost_config=ExecutionCostConfig(taker_fee_bps=0.0, fallback_spread_bps=0.0, slippage_bps=0.0),
    )

    summary = report.summaries[0]

    assert summary.evaluated_fold_count == 2
    assert summary.passing_fold_count == 2
    assert summary.total_trade_count == 2
    assert summary.status == "keep_testing"
    assert summary.reason == "insufficient_total_trades"


def test_strategy_regime_walk_forward_requires_enough_folds():
    bars = [_bar(index, 100.0 + index) for index in range(4)]
    report = evaluate_strategy_regime_walk_forward(
        [_trade(2, 2.0)],
        bars,
        train_window_bars=1,
        test_window_bars=2,
        min_folds=3,
        min_passing_folds=2,
        initial_capital_eur=100.0,
        order_notional_eur=10.0,
        cost_config=ExecutionCostConfig(taker_fee_bps=0.0, fallback_spread_bps=0.0, slippage_bps=0.0),
    )

    assert report.summaries[0].status == "keep_testing"
    assert report.summaries[0].reason == "insufficient_evaluated_folds"
