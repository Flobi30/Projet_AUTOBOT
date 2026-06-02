from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research.backtest_engine import BacktestConfig, BacktestEngine
from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.market_data_repository import MarketBar
from autobot.v2.research.strategy_signal_generators import (
    GridResearchConfig,
    GridResearchSignalGenerator,
    MeanReversionResearchConfig,
    MeanReversionResearchSignalGenerator,
    TrendResearchConfig,
    TrendResearchSignalGenerator,
)
from autobot.v2.research.trade_journal import TradeJournal


pytestmark = pytest.mark.integration


def _bar(index, close, symbol="TRXEUR"):
    timestamp = datetime(2026, 5, 31, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=index)
    return MarketBar(
        timestamp=timestamp,
        symbol=symbol,
        timeframe="1m",
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=1000.0,
    )


def _backtest_config(tmp_path, strategy_id):
    return BacktestConfig(
        run_id=f"pytest_{strategy_id}",
        strategy_id=strategy_id,
        dataset_id="inline_research_signals",
        hypothesis=f"{strategy_id} research signal generator",
        initial_capital_eur=1000.0,
        default_order_notional_eur=100.0,
        output_dir=tmp_path,
        min_closed_trades=1,
        min_profit_factor=1.0,
        cost_config=ExecutionCostConfig(
            taker_fee_bps=0.0,
            fallback_spread_bps=0.0,
            slippage_bps=0.0,
            latency_buffer_bps=0.0,
        ),
    )


def test_grid_research_generator_produces_support_entry_and_take_profit(tmp_path):
    generator = GridResearchSignalGenerator(
        GridResearchConfig(range_percent=4.0, num_levels=5, entry_touch_bps=20.0, take_profit_bps=40.0)
    )
    bars = [_bar(0, 100.0), _bar(1, 99.05), _bar(2, 99.6)]

    result = BacktestEngine(_backtest_config(tmp_path, "dynamic_grid")).run(bars, generator, write_reports=False)

    assert result.signal_count == 2
    assert result.trade_count == 1
    assert result.metrics.total_net_pnl_eur > 0.0
    assert result.decision.live_promotion_allowed is False


def test_trend_research_generator_uses_prior_breakout_and_exits_on_reversal(tmp_path):
    generator = TrendResearchSignalGenerator(
        TrendResearchConfig(
            breakout_window=3,
            exit_window=2,
            momentum_window=2,
            atr_window=2,
            confirm_bps=10.0,
            min_momentum_bps=20.0,
            min_atr_bps=1.0,
            trailing_atr_mult=1.0,
            stop_atr_mult=1.0,
        )
    )
    bars = [_bar(index, price) for index, price in enumerate([100.0, 101.0, 102.0, 104.0, 106.0, 101.0])]

    result = BacktestEngine(_backtest_config(tmp_path, "trend_momentum")).run(bars, generator, write_reports=False)

    assert result.signal_count == 2
    assert result.trade_count == 1
    assert result.metrics.total_net_pnl_eur < 0.0
    assert result.decision.live_promotion_allowed is False


def test_trend_research_generator_can_test_cost_buffer_take_profit(tmp_path):
    generator = TrendResearchSignalGenerator(
        TrendResearchConfig(
            breakout_window=2,
            exit_window=2,
            momentum_window=1,
            atr_window=1,
            confirm_bps=1.0,
            min_momentum_bps=1.0,
            min_atr_bps=1.0,
            trailing_atr_mult=100.0,
            stop_atr_mult=100.0,
            exit_mode="cost_buffer_tp",
            take_profit_bps=50.0,
        )
    )
    bars = [_bar(index, price) for index, price in enumerate([100.0, 101.0, 103.0, 104.0])]

    result = BacktestEngine(_backtest_config(tmp_path, "trend_momentum")).run(bars, generator)
    journal = TradeJournal.from_json(result.journal_path)

    assert result.signal_count == 2
    assert result.trade_count == 1
    assert journal.records[0].exit_reason == "trend_cost_buffer_take_profit"
    assert journal.records[0].metadata["exit"]["exit_mode"] == "cost_buffer_tp"
    assert journal.records[0].metadata["exit"]["bars_in_position"] == 1
    assert result.decision.live_promotion_allowed is False


def test_trend_research_generator_can_test_mfe_trailing_exit(tmp_path):
    generator = TrendResearchSignalGenerator(
        TrendResearchConfig(
            breakout_window=2,
            exit_window=2,
            momentum_window=1,
            atr_window=1,
            confirm_bps=1.0,
            min_momentum_bps=1.0,
            min_atr_bps=1.0,
            trailing_atr_mult=100.0,
            stop_atr_mult=100.0,
            exit_mode="mfe_trailing",
            mfe_trailing_activation_bps=60.0,
            mfe_trailing_drawdown_bps=30.0,
        )
    )
    bars = [_bar(index, price) for index, price in enumerate([100.0, 101.0, 103.0, 105.0, 104.5])]

    result = BacktestEngine(_backtest_config(tmp_path, "trend_momentum")).run(bars, generator)
    journal = TradeJournal.from_json(result.journal_path)

    assert result.signal_count == 2
    assert result.trade_count == 1
    assert journal.records[0].exit_reason == "trend_mfe_trailing_exit"
    assert journal.records[0].metadata["exit"]["exit_mode"] == "mfe_trailing"
    assert journal.records[0].metadata["exit"]["giveback_bps"] > 30.0
    assert result.decision.live_promotion_allowed is False


def test_trend_research_generator_can_test_time_stop_exit(tmp_path):
    generator = TrendResearchSignalGenerator(
        TrendResearchConfig(
            breakout_window=2,
            exit_window=2,
            momentum_window=1,
            atr_window=1,
            confirm_bps=1.0,
            min_momentum_bps=1.0,
            min_atr_bps=1.0,
            trailing_atr_mult=100.0,
            stop_atr_mult=100.0,
            exit_mode="time_stop",
            max_hold_bars=2,
            min_profit_before_time_exit_bps=0.0,
        )
    )
    bars = [_bar(index, price) for index, price in enumerate([100.0, 101.0, 103.0, 103.1, 103.0])]

    result = BacktestEngine(_backtest_config(tmp_path, "trend_momentum")).run(bars, generator)
    journal = TradeJournal.from_json(result.journal_path)

    assert result.signal_count == 2
    assert result.trade_count == 1
    assert journal.records[0].exit_reason == "trend_time_stop"
    assert journal.records[0].metadata["exit"]["exit_mode"] == "time_stop"
    assert journal.records[0].metadata["exit"]["bars_in_position"] == 2
    assert result.decision.live_promotion_allowed is False


def test_mean_reversion_research_generator_uses_prior_window_and_exits_at_mean(tmp_path):
    generator = MeanReversionResearchSignalGenerator(
        MeanReversionResearchConfig(
            window=5,
            entry_z=2.0,
            exit_z=0.25,
            stop_z=5.0,
            atr_window=2,
            min_atr_bps=1.0,
            max_abs_trend_bps=1000.0,
            min_expected_edge_bps=20.0,
        )
    )
    bars = [_bar(index, price) for index, price in enumerate([100.0, 100.5, 99.5, 100.0, 100.2, 97.0, 100.0])]

    result = BacktestEngine(_backtest_config(tmp_path, "mean_reversion")).run(bars, generator, write_reports=False)

    assert result.signal_count == 2
    assert result.trade_count == 1
    assert result.metrics.total_net_pnl_eur > 0.0
    assert result.decision.live_promotion_allowed is False


def test_research_generators_expose_strategy_family_metadata():
    generator = TrendResearchSignalGenerator(
        TrendResearchConfig(
            breakout_window=2,
            momentum_window=1,
            atr_window=1,
            confirm_bps=1.0,
            min_momentum_bps=1.0,
            min_atr_bps=1.0,
        )
    )
    bars = [_bar(index, price) for index, price in enumerate([100.0, 101.0, 103.0])]
    signals = []
    for index, bar in enumerate(bars):
        signals.extend(generator(bar, bars[: index + 1]))

    assert signals
    assert signals[0].metadata["strategy_family"] == "trend"
    assert signals[0].metadata["strategy_id"] == "trend_momentum"
    assert signals[0].metadata["gross_edge_bps"] > 0.0
