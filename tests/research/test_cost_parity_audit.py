import json
import sqlite3

import pytest

from autobot.v2.research.cost_parity_audit import (
    CostParityAuditConfig,
    audit_cost_parity,
    write_cost_parity_audit_report,
)
from autobot.v2.research.execution_cost_model import ExecutionCostConfig


pytestmark = pytest.mark.unit


def _state_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE trade_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT,
                position_id TEXT,
                symbol TEXT,
                executed_price REAL,
                volume REAL,
                fees REAL,
                slippage_bps REAL,
                created_at TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, symbol, executed_price, volume, fees, slippage_bps, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("buy", "pos_1", "TRXEUR", 1.0, 100.0, 0.16, 5.0, "2026-06-04T00:00:00+00:00"),
                ("sell", "pos_1", "TRXEUR", 1.0, 100.0, 0.16, 5.0, "2026-06-04T00:01:00+00:00"),
            ],
        )


def _shadow_db(path, table="trend_shadow_trades", *, fees=0.5):
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"""
            CREATE TABLE {table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                variant TEXT,
                position_id TEXT,
                entry_price REAL,
                exit_price REAL,
                volume REAL,
                notional REAL,
                fees REAL,
                realized_pnl REAL,
                reason TEXT,
                opened_at TEXT,
                closed_at TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO {table}
            (symbol, variant, position_id, entry_price, exit_price, volume, notional, fees,
             realized_pnl, reason, opened_at, closed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "TRXEUR",
                "pytest",
                "shadow_pos_1",
                1.0,
                1.01,
                100.0,
                100.0,
                fees,
                0.5,
                "take_profit",
                "2026-06-04T00:00:00+00:00",
                "2026-06-04T00:01:00+00:00",
                "2026-06-04T00:01:00+00:00",
            ),
        )


def test_cost_parity_audit_compares_state_and_shadow_costs(tmp_path):
    state_db = tmp_path / "state.db"
    trend_db = tmp_path / "trend_shadow.db"
    _state_db(state_db)
    _shadow_db(trend_db)

    report = audit_cost_parity(
        CostParityAuditConfig(
            run_id="pytest_cost_parity",
            state_db_path=state_db,
            trend_shadow_db_path=trend_db,
            research_cost_config=ExecutionCostConfig(
                taker_fee_bps=16.0,
                fallback_spread_bps=8.0,
                slippage_bps=4.0,
                latency_buffer_bps=1.0,
            ),
        )
    )

    assert report.expected_cost_bps_per_side == pytest.approx(25.0)
    sources = {source.source: source for source in report.sources}
    paper = sources["official_paper_trade_ledger"]
    assert paper.status == "ok"
    assert paper.trade_count == 1
    assert paper.cost_row_count == 2
    assert paper.total_notional_eur == pytest.approx(200.0)
    assert paper.avg_fee_bps == pytest.approx(16.0)
    assert paper.avg_slippage_bps == pytest.approx(5.0)
    assert paper.avg_total_cost_bps == pytest.approx(21.0)
    assert paper.cost_delta_bps == pytest.approx(-4.0)
    assert paper.total_favorable_slippage_eur == pytest.approx(0.0)
    assert paper.anomalous_slippage_row_count == 0
    assert "avg_cost_below_research_expected" not in paper.warnings

    trend = sources["trend_shadow"]
    assert trend.status == "ok"
    assert trend.trade_count == 1
    assert trend.total_notional_eur == pytest.approx(200.0)
    assert trend.avg_total_cost_bps == pytest.approx(25.0)
    assert "shadow_cost_components_collapsed" in trend.warnings


def test_cost_parity_audit_flags_missing_and_too_cheap_sources(tmp_path):
    state_db = tmp_path / "missing.db"
    trend_db = tmp_path / "trend_shadow.db"
    _shadow_db(trend_db, fees=0.1)

    report = audit_cost_parity(
        CostParityAuditConfig(
            run_id="pytest_cost_parity_warnings",
            state_db_path=state_db,
            trend_shadow_db_path=trend_db,
            warning_delta_bps=1.0,
        )
    )

    sources = {source.source: source for source in report.sources}
    assert sources["official_paper_trade_ledger"].status == "missing"
    assert "state_db_missing" in sources["official_paper_trade_ledger"].warnings
    assert sources["trend_shadow"].avg_total_cost_bps == pytest.approx(5.0)
    assert "avg_cost_below_research_expected" in sources["trend_shadow"].warnings
    assert "state_db_missing" in report.warnings


def test_cost_parity_audit_separates_favorable_slippage_and_anomalies(tmp_path):
    state_db = tmp_path / "state.db"
    _state_db(state_db)
    with sqlite3.connect(state_db) as conn:
        conn.execute(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, symbol, executed_price, volume, fees, slippage_bps, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("sell", "pos_2", "TRXEUR", 1.0, 100.0, 0.16, -150.0, "2026-06-04T00:02:00+00:00"),
        )

    report = audit_cost_parity(
        CostParityAuditConfig(
            run_id="pytest_signed_slippage",
            state_db_path=state_db,
            slippage_anomaly_threshold_bps=100.0,
        )
    )

    paper = {source.source: source for source in report.sources}["official_paper_trade_ledger"]
    assert paper.total_slippage_eur == pytest.approx(0.1)
    assert paper.total_favorable_slippage_eur == pytest.approx(1.5)
    assert paper.max_abs_slippage_bps == pytest.approx(150.0)
    assert paper.anomalous_slippage_row_count == 1
    assert "slippage_bps_anomalies" in paper.warnings


def test_cost_parity_report_writer_outputs_json_and_markdown(tmp_path):
    state_db = tmp_path / "state.db"
    _state_db(state_db)
    report = audit_cost_parity(CostParityAuditConfig(run_id="pytest_cost_report", state_db_path=state_db))

    written = write_cost_parity_audit_report(report, tmp_path / "reports")

    assert written.json_report_path
    assert written.markdown_report_path
    payload = json.loads((tmp_path / "reports" / "pytest_cost_report.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "reports" / "pytest_cost_report.md").read_text(encoding="utf-8")
    assert payload["run_id"] == "pytest_cost_report"
    assert "Cost Parity Audit" in markdown
    assert "No live trading permission is granted." in markdown
