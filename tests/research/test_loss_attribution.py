from datetime import datetime, timezone

import pytest

from autobot.v2.research.loss_attribution import (
    analyze_trade_journal,
    analyze_trade_losses,
    render_loss_attribution_report,
    write_matrix_loss_attribution_report,
    write_loss_attribution_report,
)
from autobot.v2.research.trade_journal import TradeJournal, TradeRecord
from autobot.v2.research.validation_matrix import MatrixCellResult, MatrixRunResult


pytestmark = pytest.mark.unit


def _trade(
    *,
    net,
    gross,
    symbol="TRXEUR",
    entry_reason="grid_touch",
    exit_reason="take_profit",
    fees=0.1,
    slippage=0.05,
    spread=0.02,
    metadata=None,
):
    return TradeRecord(
        run_id="pytest_loss_run",
        strategy_id="dynamic_grid",
        symbol=symbol,
        side="long",
        opened_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 1, 10, 5, tzinfo=timezone.utc),
        quantity=10.0,
        entry_price=1.0,
        exit_price=1.01,
        gross_pnl_eur=gross,
        net_pnl_eur=net,
        fees_eur=fees,
        slippage_eur=slippage,
        spread_cost_eur=spread,
        entry_reason=entry_reason,
        exit_reason=exit_reason,
        metadata=dict(metadata or {}),
    )


def test_loss_attribution_tracks_cost_drag_and_cost_flipped_trades():
    result = analyze_trade_losses(
        [
            _trade(
                gross=0.5,
                net=0.25,
                metadata={
                    "path": {
                        "max_favorable_excursion_bps": 40.0,
                        "max_adverse_excursion_bps": -5.0,
                        "entry_to_exit_bps": 20.0,
                        "mfe_giveback_bps": 20.0,
                        "mfe_capture_ratio": 0.5,
                        "positive_mfe_capture_ratio": 0.5,
                        "total_cost_bps": 20.0,
                        "mfe_to_cost_ratio": 2.0,
                    }
                },
            ),
            _trade(
                gross=0.1,
                net=-0.05,
                exit_reason="cost_stop",
                metadata={
                    "path": {
                        "max_favorable_excursion_bps": 25.0,
                        "max_adverse_excursion_bps": -30.0,
                        "entry_to_exit_bps": -5.0,
                        "mfe_giveback_bps": 30.0,
                        "mfe_capture_ratio": -0.2,
                        "positive_mfe_capture_ratio": 0.0,
                        "total_cost_bps": 20.0,
                        "mfe_to_cost_ratio": 1.25,
                    }
                },
            ),
            _trade(gross=-0.4, net=-0.6, symbol="XLMZEUR", exit_reason="stop_loss"),
        ]
    )

    assert result.trade_count == 3
    assert result.gross_pnl_eur == pytest.approx(0.2)
    assert result.net_pnl_eur == pytest.approx(-0.4)
    assert result.total_cost_eur == pytest.approx(0.51)
    assert result.cost_flipped_trade_count == 1
    assert result.mfe_above_cost_trade_count == 2
    assert result.mfe_above_cost_lost_trade_count == 1
    assert result.average_mfe_bps == pytest.approx(32.5)
    assert result.average_mae_bps == pytest.approx(-17.5)
    assert result.average_exit_capture_bps == pytest.approx(7.5)
    assert result.average_mfe_giveback_bps == pytest.approx(25.0)
    assert result.average_mfe_capture_ratio == pytest.approx(0.15)
    assert result.average_positive_mfe_capture_ratio == pytest.approx(0.25)
    assert result.average_mfe_to_cost_ratio == pytest.approx(1.625)
    assert result.losing_trade_count == 2
    assert result.winning_trade_count == 1
    assert [bucket.key for bucket in result.by_failure_mode] == [
        "stop_loss_adverse_move",
        "cost_flipped_positive_gross",
        "profitable",
    ]
    assert result.by_exit_reason[0].key == "stop_loss"
    assert {bucket.key for bucket in result.by_symbol} == {"TRXEUR", "XLMZEUR"}


def test_loss_attribution_report_writer_round_trips_journal(tmp_path):
    journal_path = tmp_path / "journal.json"
    TradeJournal([_trade(gross=0.5, net=0.25)]).to_json(journal_path)

    result = write_loss_attribution_report(analyze_trade_journal(journal_path), tmp_path / "reports")
    markdown = render_loss_attribution_report(result)

    assert result.json_report_path
    assert result.markdown_report_path
    assert (tmp_path / "reports" / "pytest_loss_run_loss_attribution.json").exists()
    assert "Cost-Flipped Trades" in markdown
    assert "Average MFE" in markdown
    assert "By Failure Mode" in markdown
    assert "Research Recommendations" in markdown
    assert "Dominant failure mode" in markdown
    assert "research-only" in markdown


def test_matrix_loss_attribution_finds_cell_journals_and_summarizes(tmp_path):
    backtest_dir = tmp_path / "cells" / "backtests"
    backtest_dir.mkdir(parents=True)
    report_path = backtest_dir / "cell_run.md"
    report_path.write_text("# cell", encoding="utf-8")
    TradeJournal(
        [
            _trade(
                gross=0.5,
                net=0.25,
                metadata={
                    "path": {
                        "max_favorable_excursion_bps": 40.0,
                        "max_adverse_excursion_bps": -5.0,
                        "entry_to_exit_bps": 20.0,
                        "mfe_giveback_bps": 20.0,
                        "mfe_capture_ratio": 0.5,
                        "positive_mfe_capture_ratio": 0.5,
                        "total_cost_bps": 20.0,
                        "mfe_to_cost_ratio": 2.0,
                    }
                },
            ),
            _trade(
                gross=0.1,
                net=-0.05,
                exit_reason="cost_stop",
                metadata={
                    "path": {
                        "max_favorable_excursion_bps": 25.0,
                        "max_adverse_excursion_bps": -30.0,
                        "entry_to_exit_bps": -5.0,
                        "mfe_giveback_bps": 30.0,
                        "mfe_capture_ratio": -0.2,
                        "positive_mfe_capture_ratio": 0.0,
                        "total_cost_bps": 20.0,
                        "mfe_to_cost_ratio": 1.25,
                    }
                },
            ),
        ]
    ).to_json(backtest_dir / "cell_run_journal.json")
    matrix = MatrixRunResult(
        run_id="pytest_matrix",
        mode="backtest",
        cell_count=1,
        success_count=1,
        error_count=0,
        results=(
            MatrixCellResult(
                run_id="cell_run",
                symbol="TRXEUR",
                strategy="grid",
                mode="backtest",
                status="ok",
                decision="modify",
                reason="cost_drag",
                closed_trades=2,
                net_pnl_eur=0.2,
                report_path=str(report_path),
            ),
        ),
    )

    report = write_matrix_loss_attribution_report(matrix, tmp_path / "losses")

    assert report.analyzed_cell_count == 1
    assert report.total_trades == 2
    assert report.aggregate_cost_flipped_trade_count == 1
    assert report.aggregate_mfe_above_cost_trade_count == 2
    assert report.aggregate_mfe_above_cost_lost_trade_count == 1
    assert report.aggregate_average_mfe_bps == pytest.approx(32.5)
    assert report.aggregate_average_mae_bps == pytest.approx(-17.5)
    assert report.aggregate_average_exit_capture_bps == pytest.approx(7.5)
    assert report.aggregate_average_mfe_giveback_bps == pytest.approx(25.0)
    assert report.aggregate_average_mfe_capture_ratio == pytest.approx(0.15)
    assert report.aggregate_average_positive_mfe_capture_ratio == pytest.approx(0.25)
    assert report.aggregate_average_mfe_to_cost_ratio == pytest.approx(1.625)
    assert report.cells[0].worst_exit_reason == "cost_stop"
    assert report.cells[0].primary_failure_mode == "cost_flipped_positive_gross"
    assert [bucket.key for bucket in report.by_failure_mode] == ["cost_flipped_positive_gross", "profitable"]
    assert (tmp_path / "losses" / "pytest_matrix_matrix_loss_attribution.md").exists()
