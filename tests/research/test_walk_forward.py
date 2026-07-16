from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research.backtest_engine import BacktestConfig, BacktestSignal
from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.market_data_repository import MarketBar
from autobot.v2.research.walk_forward import WalkForwardConfig, WalkForwardValidator


pytestmark = pytest.mark.integration


def _bar(index, close):
    timestamp = datetime(2026, 5, 31, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=index)
    return MarketBar(
        timestamp=timestamp,
        symbol="TRXEUR",
        timeframe="1m",
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=1000.0,
    )


def _base_config(tmp_path, *, min_closed_trades=2):
    return BacktestConfig(
        run_id="wf_base",
        strategy_id="example_strategy",
        dataset_id="inline_walk_forward",
        hypothesis="walk-forward validation test",
        initial_capital_eur=1000.0,
        default_order_notional_eur=1000.0,
        output_dir=tmp_path,
        min_closed_trades=min_closed_trades,
        min_profit_factor=1.1,
        cost_config=ExecutionCostConfig(
            taker_fee_bps=0.0,
            fallback_spread_bps=0.0,
            slippage_bps=0.0,
            latency_buffer_bps=0.0,
        ),
    )


def _two_trade_strategy_factory(seen_history_lengths=None):
    def strategy(bar, history):
        if seen_history_lengths is not None:
            seen_history_lengths.append(len(history))
        if len(history) == 1:
            return [BacktestSignal(symbol=bar.symbol, side="buy", price=bar.close, timestamp=bar.timestamp, reason="entry_1")]
        if len(history) == 2:
            return [BacktestSignal(symbol=bar.symbol, side="sell", price=bar.close, timestamp=bar.timestamp, reason="exit_1")]
        if len(history) == 3:
            return [BacktestSignal(symbol=bar.symbol, side="buy", price=bar.close, timestamp=bar.timestamp, reason="entry_2")]
        if len(history) == 4:
            return [BacktestSignal(symbol=bar.symbol, side="sell", price=bar.close, timestamp=bar.timestamp, reason="exit_2")]
        return []

    return strategy


def test_walk_forward_uses_only_test_window_history_and_writes_reports(tmp_path):
    seen_history_lengths = []
    bars = [_bar(index, price) for index, price in enumerate([0.9, 1.0, 1.2, 1.2, 1.19, 0.8])]
    config = WalkForwardConfig(
        run_id="pytest_wf",
        base_backtest_config=_base_config(tmp_path),
        train_window_bars=1,
        test_window_bars=5,
        min_folds=1,
        min_passing_folds=1,
        output_dir=tmp_path,
    )

    result = WalkForwardValidator(config).run(
        bars,
        lambda: _two_trade_strategy_factory(seen_history_lengths),
    )

    assert seen_history_lengths == [1, 2, 3, 4, 5]
    assert result.fold_count == 1
    assert result.total_closed_trades == 2
    assert result.decision.live_promotion_allowed is False
    assert (tmp_path / "pytest_wf.md").exists()
    assert (tmp_path / "pytest_wf.json").exists()


def test_walk_forward_blocks_when_not_enough_folds(tmp_path):
    bars = [_bar(index, 1.0 + index * 0.01) for index in range(6)]
    config = WalkForwardConfig(
        run_id="pytest_wf_short",
        base_backtest_config=_base_config(tmp_path, min_closed_trades=1),
        train_window_bars=2,
        test_window_bars=2,
        min_folds=3,
        min_passing_folds=2,
        output_dir=tmp_path,
    )

    result = WalkForwardValidator(config).run(bars, lambda: _two_trade_strategy_factory(), write_reports=False)

    assert result.fold_count < 3
    assert result.decision.status == "keep_testing"
    assert result.decision.reason == "insufficient_walk_forward_folds"


def test_walk_forward_can_pass_only_after_enough_passing_folds(tmp_path):
    bars = []
    for offset in (0, 6):
        bars.extend(
            [
                _bar(offset + 0, 0.9),
                _bar(offset + 1, 1.5),
                _bar(offset + 2, 1.0),
                _bar(offset + 3, 2.0),
                _bar(offset + 4, 2.0),
                _bar(offset + 5, 1.9),
            ]
        )
    config = WalkForwardConfig(
        run_id="pytest_wf_pass_next_open_1",
        base_backtest_config=_base_config(tmp_path),
        train_window_bars=1,
        test_window_bars=5,
        step_window_bars=6,
        min_folds=2,
        min_passing_folds=2,
        output_dir=tmp_path,
    )

    result = WalkForwardValidator(config).run(bars, lambda: _two_trade_strategy_factory(), write_reports=False)

    assert result.fold_count == 2
    assert result.passing_fold_count == 2
    assert result.decision.status == "walk_forward_passed"
    assert result.decision.proposed_registry_status == "walk_forward_passed"
    assert result.decision.live_promotion_allowed is False
