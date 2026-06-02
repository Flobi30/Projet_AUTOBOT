from datetime import datetime, timezone

import pytest

from autobot.v2.research.setup_quality import (
    analyze_setup_quality,
    analyze_setup_quality_journal,
    render_setup_quality_report,
    write_setup_quality_report,
)
from autobot.v2.research.trade_journal import TradeJournal, TradeRecord


pytestmark = pytest.mark.unit


def _trade(
    *,
    net,
    gross,
    breakout,
    momentum,
    atr,
    regime="trend",
    symbol="XLMZEUR",
    mfe=80.0,
    mae=-20.0,
    exit_bps=20.0,
    mfe_to_cost=2.0,
    total_cost_bps=40.0,
):
    return TradeRecord(
        run_id="pytest_setup_quality",
        strategy_id="trend_momentum",
        symbol=symbol,
        side="long",
        opened_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 1, 10, 5, tzinfo=timezone.utc),
        quantity=10.0,
        entry_price=1.0,
        exit_price=1.01,
        gross_pnl_eur=gross,
        net_pnl_eur=net,
        fees_eur=0.1,
        slippage_eur=0.05,
        spread_cost_eur=0.02,
        entry_reason="trend_breakout",
        exit_reason="trend_exit",
        regime=regime,
        metadata={
            "entry": {
                "strategy_family": "trend",
                "breakout_bps": breakout,
                "momentum_bps": momentum,
                "atr_bps": atr,
                "regime": regime,
            },
            "path": {
                "max_favorable_excursion_bps": mfe,
                "max_adverse_excursion_bps": mae,
                "entry_to_exit_bps": exit_bps,
                "mfe_to_cost_ratio": mfe_to_cost,
                "total_cost_bps": total_cost_bps,
            },
        },
    )


def _bucket_map(buckets):
    return {bucket.key: bucket for bucket in buckets}


def test_setup_quality_groups_entries_by_strength_and_regime():
    report = analyze_setup_quality(
        [
            _trade(net=1.0, gross=1.3, breakout=120.0, momentum=150.0, atr=60.0, regime="trend"),
            _trade(
                net=-0.5,
                gross=-0.2,
                breakout=20.0,
                momentum=25.0,
                atr=8.0,
                regime="range",
                mfe=15.0,
                exit_bps=-15.0,
                mfe_to_cost=0.3,
            ),
            _trade(
                net=-0.2,
                gross=0.1,
                breakout=65.0,
                momentum=70.0,
                atr=30.0,
                regime="trend",
                mfe=70.0,
                exit_bps=-5.0,
                mfe_to_cost=1.4,
            ),
        ]
    )

    breakout = _bucket_map(report.by_breakout_strength)
    momentum = _bucket_map(report.by_momentum_strength)
    atr = _bucket_map(report.by_atr_regime)
    regimes = _bucket_map(report.by_regime)

    assert report.trade_count == 3
    assert report.net_pnl_eur == pytest.approx(0.3)
    assert report.cost_dominated_trade_count == 1
    assert report.mfe_above_cost_lost_trade_count == 1
    assert breakout["weak_lt_40"].trade_count == 1
    assert breakout["medium_40_80"].mfe_above_cost_lost_trade_count == 1
    assert breakout["strong_gte_80"].win_count == 1
    assert momentum["strong_gte_100"].average_mfe_bps == pytest.approx(80.0)
    assert atr["weak_lt_15"].cost_dominated_trade_count == 1
    assert regimes["trend"].trade_count == 2


def test_setup_quality_report_writer_round_trips_journal(tmp_path):
    journal_path = tmp_path / "journal.json"
    TradeJournal(
        [
            _trade(net=1.0, gross=1.3, breakout=120.0, momentum=150.0, atr=60.0),
            _trade(net=-0.2, gross=0.1, breakout=65.0, momentum=70.0, atr=30.0),
        ]
    ).to_json(journal_path)

    result = write_setup_quality_report(analyze_setup_quality_journal(journal_path), tmp_path / "reports")
    markdown = render_setup_quality_report(result)

    assert result.json_report_path
    assert result.markdown_report_path
    assert (tmp_path / "reports" / "pytest_setup_quality_setup_quality.json").exists()
    assert "By Breakout Strength" in markdown
    assert "MFE Above Cost Lost Trades" in markdown
    assert "research-only" in markdown
