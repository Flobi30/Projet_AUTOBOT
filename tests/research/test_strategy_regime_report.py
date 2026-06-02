from datetime import datetime, timezone

import pytest

from autobot.v2.research.strategy_regime_report import (
    analyze_strategy_regimes,
    load_strategy_regime_report,
    render_strategy_regime_report,
    write_strategy_regime_report,
)
from autobot.v2.research.trade_journal import TradeRecord


pytestmark = pytest.mark.unit


def _trade(strategy, regime, net, *, symbol="TRXEUR", mfe_to_cost=2.0):
    return TradeRecord(
        run_id="pytest_strategy_regime",
        strategy_id=strategy,
        symbol=symbol,
        side="long",
        opened_at=datetime(2026, 6, 2, 8, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 2, 8, 5, tzinfo=timezone.utc),
        quantity=10.0,
        entry_price=1.0,
        exit_price=1.01,
        gross_pnl_eur=net + 0.25,
        net_pnl_eur=net,
        fees_eur=0.1,
        slippage_eur=0.05,
        spread_cost_eur=0.02,
        entry_reason="entry",
        exit_reason="exit",
        regime=regime,
        metadata={
            "entry": {"strategy_id": strategy, "regime": regime},
            "path": {
                "max_favorable_excursion_bps": 80.0,
                "entry_to_exit_bps": 25.0,
                "mfe_to_cost_ratio": mfe_to_cost,
                "total_cost_bps": 40.0,
            },
        },
    )


def test_strategy_regime_report_groups_by_strategy_and_regime(tmp_path):
    report = analyze_strategy_regimes(
        [
            _trade("dynamic_grid", "range", 1.0),
            _trade("dynamic_grid", "range", -0.4, mfe_to_cost=0.4),
            _trade("trend_momentum", "chaos", 0.5, symbol="XLMZEUR"),
        ]
    )

    buckets = {(bucket.strategy_id, bucket.regime): bucket for bucket in report.buckets}

    assert report.trade_count == 3
    assert report.net_pnl_eur == pytest.approx(1.1)
    assert buckets[("dynamic_grid", "range")].trade_count == 2
    assert buckets[("dynamic_grid", "range")].cost_dominated_trade_count == 1
    assert buckets[("trend_momentum", "chaos")].symbols == ("XLMZEUR",)

    written = write_strategy_regime_report(report, tmp_path)
    markdown = render_strategy_regime_report(written)

    assert written.json_report_path
    assert written.markdown_report_path
    assert "Strategy x Regime" in markdown
    assert "research-only" in markdown

    reloaded = load_strategy_regime_report(written.json_report_path)

    assert reloaded.run_id == "pytest_strategy_regime"
    assert reloaded.trade_count == 3
    assert reloaded.buckets[0].symbols
