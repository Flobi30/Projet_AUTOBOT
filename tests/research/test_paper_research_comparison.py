from datetime import datetime, timezone

import pytest

from autobot.v2.research.decision_trace_audit import (
    DecisionTrace,
    DecisionTraceAuditConfig,
    DecisionTraceAuditReport,
    DecisionTraceAuditSummary,
)
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


def _matrix_cell(strategy="trend", symbol="TRXEUR", net=-3.0, trades=2, include_costs=False):
    costs = {}
    if include_costs:
        costs = {
            "fees_eur": 0.4,
            "spread_cost_eur": 0.2,
            "slippage_eur": 0.1,
            "latency_cost_eur": 0.05,
            "cost_config": {"taker_fee_bps": 16.0, "fallback_spread_bps": 8.0, "slippage_bps": 4.0},
        }
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
        **costs,
    )


def _decision_trace_report():
    trace = DecisionTrace(
        trace_id="decision_id:dec_1",
        decision_id="dec_1",
        signal_id="sig_1",
        symbol="TRXEUR",
        strategy="grid",
        engine="trend_momentum",
        first_seen_at="2026-06-03T09:00:00+00:00",
        event_types=("decision",),
        event_statuses=("accepted",),
        reasons=("risk_accepted",),
        has_signal=False,
        has_decision=True,
        is_rejected=False,
        is_execution_path=True,
        has_order=True,
        has_fill=False,
        has_trade=False,
        has_pnl=False,
        has_outcome=False,
        net_pnl_eur=0.0,
        outcome_labels=(),
        missing_stages=("signal", "fill", "trade", "pnl"),
        canonical_complete=False,
    )
    return DecisionTraceAuditReport(
        run_id="trace_run",
        generated_at="2026-06-03T11:00:00+00:00",
        config=DecisionTraceAuditConfig(state_db_path="memory", run_id="trace_run"),
        data_sources={"status": "pytest"},
        summary=DecisionTraceAuditSummary(
            trace_count=1,
            canonical_complete_count=0,
            canonical_complete_ratio=0.0,
            signal_without_decision_count=0,
            rejected_trace_count=0,
            rejected_with_outcome_count=0,
            execution_trace_count=1,
            execution_complete_count=0,
            orphan_order_count=0,
            orphan_trade_count=0,
            total_net_pnl_eur=0.0,
            missing_stage_counts={"fill": 1, "pnl": 1, "signal": 1, "trade": 1},
            event_type_counts={"decision": 1},
            event_status_counts={"accepted": 1},
        ),
        traces=(trace,),
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
    assert "runtime_or_sample_difference" in bucket.diagnostics
    assert "research_rejected_negative_net_pnl" in bucket.diagnostics
    assert "paper_research_divergence" in bucket.warnings


def test_compare_paper_to_research_attaches_decision_trace_diagnostics():
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
        run_id="compare_with_trace",
        paper_source_type="pytest",
        paper_source_path="memory",
        decision_trace_report=_decision_trace_report(),
    )

    bucket = report.buckets[0]
    assert report.decision_trace_run_id == "trace_run"
    assert bucket.decision_traces is not None
    assert bucket.decision_traces.trace_count == 1
    assert bucket.decision_traces.canonical_complete_ratio == 0.0
    assert "decision_trace_execution_incomplete" in bucket.diagnostics
    assert "decision_trace_missing_fill" in bucket.diagnostics
    assert "decision_trace_missing_trade" in bucket.diagnostics


def test_compare_paper_to_research_uses_research_cost_breakdown_when_available():
    journal = TradeJournal([_trade(net=5.0)])
    matrix = MatrixRunResult(
        run_id="matrix_run",
        mode="backtest",
        cell_count=1,
        success_count=1,
        error_count=0,
        results=(_matrix_cell(net=-3.0, include_costs=True),),
    )

    report = compare_paper_to_research(
        journal,
        matrix,
        run_id="compare_with_costs",
        paper_source_type="pytest",
        paper_source_path="memory",
    )

    bucket = report.buckets[0]
    assert bucket.research.fees_eur == pytest.approx(0.4)
    assert bucket.research.spread_cost_eur == pytest.approx(0.2)
    assert bucket.research.slippage_eur == pytest.approx(0.1)
    assert "research_cost_breakdown_unavailable_from_matrix_summary" not in bucket.diagnostics


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
    assert "research_adapter_missing_official_paper_trades" in report.buckets[0].diagnostics


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
    markdown = (tmp_path / "compare_write.md").read_text(encoding="utf-8")
    assert "Diagnostics" in markdown
    assert "both_sources_unprofitable" in markdown
