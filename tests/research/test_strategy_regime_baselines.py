from datetime import datetime, timezone

import pytest

from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.market_data_repository import MarketBar
from autobot.v2.research.strategy_regime_baselines import (
    evaluate_strategy_regime_baselines,
    render_strategy_regime_baseline_report,
    write_strategy_regime_baseline_report,
)
from autobot.v2.research.strategy_regime_report import analyze_strategy_regimes
from autobot.v2.research.trade_journal import TradeRecord


pytestmark = pytest.mark.unit


def _bar(minute, close, *, regime="range"):
    timestamp = datetime(2026, 6, 2, 8, minute, tzinfo=timezone.utc)
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


def _trade(net, *, regime="range"):
    return TradeRecord(
        run_id="pytest_regime_baseline",
        strategy_id="dynamic_grid",
        symbol="TRXEUR",
        side="long",
        opened_at=datetime(2026, 6, 2, 8, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 2, 8, 2, tzinfo=timezone.utc),
        quantity=1.0,
        entry_price=100.0,
        exit_price=101.0,
        gross_pnl_eur=net,
        net_pnl_eur=net,
        regime=regime,
        metadata={"entry": {"strategy_id": "dynamic_grid", "regime": regime}},
    )


def test_strategy_regime_baselines_compare_bucket_to_references(tmp_path):
    strategy_report = analyze_strategy_regimes([_trade(2.0)], run_id="pytest_strategy_regime")
    report = evaluate_strategy_regime_baselines(
        strategy_report,
        [_bar(0, 100.0), _bar(1, 100.5), _bar(2, 101.0)],
        initial_capital_eur=100.0,
        order_notional_eur=10.0,
        cost_config=ExecutionCostConfig(taker_fee_bps=0.0, fallback_spread_bps=0.0, slippage_bps=0.0),
    )

    bucket = report.buckets[0]
    baseline_names = {baseline.name for baseline in bucket.baselines}

    assert baseline_names == {
        "no_trade",
        "buy_and_hold_regime_segments",
        "random_signal_same_frequency_regime",
    }
    assert bucket.best_baseline_name == "buy_and_hold_regime_segments"
    assert bucket.strategy_net_pnl_eur == pytest.approx(2.0)
    assert bucket.beats_no_trade is True
    assert bucket.beats_best_baseline is True

    written = write_strategy_regime_baseline_report(report, tmp_path)
    markdown = render_strategy_regime_baseline_report(written)

    assert written.json_report_path
    assert written.markdown_report_path
    assert "Strategy Regime Baseline Report" in markdown
    assert "research-only" in markdown


def test_strategy_regime_baselines_do_not_overstate_negative_bucket():
    strategy_report = analyze_strategy_regimes([_trade(-1.0)], run_id="pytest_strategy_regime")
    report = evaluate_strategy_regime_baselines(
        strategy_report,
        [_bar(0, 100.0), _bar(1, 99.0)],
        initial_capital_eur=100.0,
        order_notional_eur=10.0,
        cost_config=ExecutionCostConfig(taker_fee_bps=0.0, fallback_spread_bps=0.0, slippage_bps=0.0),
    )

    bucket = report.buckets[0]

    assert bucket.strategy_net_pnl_eur == pytest.approx(-1.0)
    assert bucket.beats_no_trade is False
    assert bucket.beats_best_baseline is False
