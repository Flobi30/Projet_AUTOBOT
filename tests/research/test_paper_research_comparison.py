from datetime import datetime, timezone

import pytest

from autobot.v2.research.paper_research_comparison import (
    compare_paper_to_research,
    write_paper_research_comparison_report,
)
from autobot.v2.research.trade_journal import TradeJournal, TradeRecord
from autobot.v2.research.validation_matrix import MatrixCellResult, MatrixRunResult


pytestmark = pytest.mark.unit


def _trade(strategy_id="trend_momentum", symbol="TRXEUR", net=5.0):
    return TradeRecord(
        run_id="paper",
        strategy_id=strategy_id,
        symbol=symbol,
        side="buy",
        opened_at=datetime(2026, 6, 3, 9, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 3, 10, tzinfo=timezone.utc),
        quantity=10.0,
        entry_price=1.0,
        exit_price=1.5,
        gross_pnl_eur=net + 0.4,
        net_pnl_eur=net,
        fees_eur=0.4,
        slippage_eur=0.1,
        entry_reason="accepted",
        exit_reason="take_profit",
    )


def _matrix_cell(strategy="trend", symbol="TRXEUR", net=-3.0, trades=2):
    return MatrixCellResult(
        run_id=f"matrix_{symbol}_{strategy}",
        symbol=symbol,
        strategy=strategy,
        mode="backtest",
        status="ok",
        decision="modify",
        reason="non_positive_net_pnl",
        bar_count=100,
        closed_trades=trades,
        net_pnl_eur=net,
        total_return_pct=net / 10.0,
        profit_factor=0.7,
        max_drawdown_pct=2.0,
    )


def test_compare_paper_to_research_detects_strategy_symbol_divergence():
    journal = TradeJournal([_trade(net=5.0)])
    matrix = MatrixRunResult(
        run_id="matrix_run",
        mode="backtest",
        cell_count=1,
        success_count=1,
        error_count=0,
        results=(_matrix_cell(net=-3.0),),
    )

    report = compare_paper_to_research(
        journal,
        matrix,
        run_id="compare",
        paper_source_type="pytest",
        paper_source_path="memory",
    )

    assert report.bucket_count == 1
    assert report.divergent_bucket_count == 1
    assert report.paper_trade_count == 1
    assert report.research_trade_count == 2
    bucket = report.buckets[0]
    assert bucket.strategy_id == "trend_momentum"
    assert bucket.symbol == "TRXEUR"
    assert bucket.alignment == "paper_positive_research_negative"
    assert bucket.delta_net_pnl_eur == pytest.approx(8.0)
    assert "paper_research_divergence" in bucket.warnings


def test_compare_paper_to_research_reports_missing_research_coverage():
    journal = TradeJournal([_trade(strategy_id="dynamic_grid", symbol="ETHEUR", net=-2.0)])
    matrix = MatrixRunResult(
        run_id="matrix_run",
        mode="backtest",
        cell_count=0,
        success_count=0,
        error_count=0,
        results=(),
    )

    report = compare_paper_to_research(
        journal,
        matrix,
        run_id="compare_missing",
        paper_source_type="pytest",
        paper_source_path="memory",
    )

    assert report.bucket_count == 1
    assert report.divergent_bucket_count == 1
    assert report.buckets[0].alignment == "paper_has_trades_research_missing"
    assert report.buckets[0].recommendation == "check_research_adapter_coverage"


def test_write_paper_research_comparison_report(tmp_path):
    report = compare_paper_to_research(
        TradeJournal([_trade(net=-1.0)]),
        MatrixRunResult(
            run_id="matrix_run",
            mode="backtest",
            cell_count=1,
            success_count=1,
            error_count=0,
            results=(_matrix_cell(net=-2.0),),
        ),
        run_id="compare_write",
        paper_source_type="pytest",
        paper_source_path="memory",
    )

    written = write_paper_research_comparison_report(report, tmp_path)

    assert written.json_report_path
    assert written.markdown_report_path
    assert (tmp_path / "compare_write.json").exists()
    assert (tmp_path / "compare_write.md").exists()
