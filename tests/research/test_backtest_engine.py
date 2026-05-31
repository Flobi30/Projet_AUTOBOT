from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research.backtest_engine import BacktestConfig, BacktestEngine, BacktestSignal
from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.market_data_repository import MarketBar


pytestmark = pytest.mark.integration


def _bar(minute, close, symbol="TRXEUR"):
    timestamp = datetime(2026, 5, 31, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=minute)
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


def _config(tmp_path, *, min_closed_trades=1):
    return BacktestConfig(
        run_id="pytest_backtest",
        strategy_id="example_strategy",
        dataset_id="inline_bars",
        hypothesis="unit replay",
        initial_capital_eur=1000.0,
        default_order_notional_eur=100.0,
        output_dir=tmp_path,
        min_closed_trades=min_closed_trades,
        cost_config=ExecutionCostConfig(
            taker_fee_bps=10.0,
            fallback_spread_bps=10.0,
            slippage_bps=5.0,
            latency_buffer_bps=1.0,
            min_notional_eur=5.0,
        ),
    )


def test_backtest_engine_replays_chronologically_and_generates_reports(tmp_path):
    seen = []

    def strategy(bar, history):
        seen.append(bar.timestamp)
        if len(history) == 1:
            return [BacktestSignal(symbol=bar.symbol, side="buy", price=bar.close, timestamp=bar.timestamp, reason="entry")]
        if len(history) == 3:
            return [BacktestSignal(symbol=bar.symbol, side="sell", price=bar.close, timestamp=bar.timestamp, reason="exit")]
        return []

    engine = BacktestEngine(_config(tmp_path))
    result = engine.run([_bar(2, 1.2), _bar(0, 1.0), _bar(1, 1.1)], strategy)

    assert seen == sorted(seen)
    assert result.event_count == 3
    assert result.signal_count == 2
    assert result.fill_count == 2
    assert result.trade_count == 1
    assert result.metrics.total_fees_eur > 0
    assert result.metrics.total_slippage_eur > 0
    assert {baseline.name for baseline in result.baselines} == {
        "no_trade",
        "buy_and_hold",
        "random_signal_same_frequency",
    }
    assert result.decision.live_promotion_allowed is False
    assert (tmp_path / "pytest_backtest.md").exists()
    assert (tmp_path / "pytest_backtest.json").exists()
    assert (tmp_path / "pytest_backtest_journal.json").exists()


def test_backtest_engine_does_not_use_future_history(tmp_path):
    history_lengths = []

    def strategy(_bar, history):
        history_lengths.append(len(history))
        return []

    engine = BacktestEngine(_config(tmp_path))
    engine.run([_bar(2, 1.2), _bar(0, 1.0), _bar(1, 1.1)], strategy, write_reports=False)

    assert history_lengths == [1, 2, 3]


def test_backtest_engine_keeps_testing_when_sample_is_too_small(tmp_path):
    def strategy(bar, history):
        if len(history) == 1:
            return [BacktestSignal(symbol=bar.symbol, side="buy", price=bar.close, timestamp=bar.timestamp, reason="entry")]
        if len(history) == 2:
            return [BacktestSignal(symbol=bar.symbol, side="sell", price=bar.close, timestamp=bar.timestamp, reason="exit")]
        return []

    engine = BacktestEngine(_config(tmp_path, min_closed_trades=30))
    result = engine.run([_bar(0, 1.0), _bar(1, 1.05)], strategy, write_reports=False)

    assert result.trade_count == 1
    assert result.decision.status == "keep_testing"
    assert result.decision.reason == "insufficient_closed_trades"


def test_backtest_engine_rejects_illiquid_signal_without_trade(tmp_path):
    def strategy(bar, history):
        if len(history) == 1:
            return [
                BacktestSignal(
                    symbol=bar.symbol,
                    side="buy",
                    price=bar.close,
                    timestamp=bar.timestamp,
                    reason="entry",
                    metadata={"liquidity_eur": 100.0},
                )
            ]
        return []

    engine = BacktestEngine(
        BacktestConfig(
            **{
                **_config(tmp_path).__dict__,
                "cost_config": ExecutionCostConfig(max_liquidity_participation=0.01),
            }
        )
    )
    result = engine.run([_bar(0, 1.0), _bar(1, 1.1)], strategy, write_reports=False)

    assert result.fill_count == 0
    assert result.rejected_fill_count == 1
    assert result.trade_count == 0


def test_backtest_engine_random_baseline_is_deterministic(tmp_path):
    def strategy(bar, history):
        if len(history) in {1, 3}:
            return [BacktestSignal(symbol=bar.symbol, side="buy", price=bar.close, timestamp=bar.timestamp, reason="entry")]
        if len(history) in {2, 4}:
            return [BacktestSignal(symbol=bar.symbol, side="sell", price=bar.close, timestamp=bar.timestamp, reason="exit")]
        return []

    bars = [_bar(0, 1.0), _bar(1, 1.02), _bar(2, 1.01), _bar(3, 1.04), _bar(4, 1.03)]
    engine = BacktestEngine(_config(tmp_path))

    first = engine.run(bars, strategy, write_reports=False)
    second = engine.run(bars, strategy, write_reports=False)

    first_random = next(baseline for baseline in first.baselines if baseline.name == "random_signal_same_frequency")
    second_random = next(baseline for baseline in second.baselines if baseline.name == "random_signal_same_frequency")
    assert first_random.net_pnl_eur == second_random.net_pnl_eur
    assert "requested trades=2" in first_random.notes
