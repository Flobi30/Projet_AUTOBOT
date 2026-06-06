import sqlite3

import pytest

from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.research_paper_parity import (
    ResearchPaperParityConfig,
    run_research_paper_parity,
    summarize_research_paper_parity,
)


pytestmark = pytest.mark.integration


def _state_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE market_price_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id TEXT,
                symbol TEXT,
                price REAL,
                observed_at TEXT,
                bucket_start TEXT,
                source TEXT,
                created_at TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO market_price_samples
            (sample_id, symbol, price, observed_at, bucket_start, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("s1", "TRXEUR", 100.0, "2026-06-01T00:00:00+00:00", "b1", "runtime", "c1"),
                ("s2", "TRXEUR", 101.0, "2026-06-01T00:01:00+00:00", "b2", "runtime", "c2"),
                ("s3", "TRXEUR", 102.0, "2026-06-01T00:02:00+00:00", "b3", "runtime", "c3"),
            ],
        )
        conn.execute(
            """
            CREATE TABLE trade_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT,
                position_id TEXT,
                instance_id TEXT,
                symbol TEXT,
                side TEXT,
                expected_price REAL,
                executed_price REAL,
                volume REAL,
                fees REAL,
                slippage_bps REAL,
                realized_pnl REAL,
                is_opening_leg INTEGER,
                is_closing_leg INTEGER,
                created_at TEXT
            )
            """
        )


def test_research_paper_parity_is_read_only_and_reports_empty_paper(tmp_path):
    state_db = tmp_path / "state.db"
    _state_db(state_db)

    report = run_research_paper_parity(
        ResearchPaperParityConfig(
            run_id="pytest_research_paper_parity",
            state_db_path=state_db,
            symbols=("TRXEUR",),
            strategies=("trend",),
            output_dir=tmp_path / "parity",
            min_closed_trades=1,
            cost_config=ExecutionCostConfig(taker_fee_bps=16.0, fallback_spread_bps=8.0, slippage_bps=4.0),
        )
    )
    summary = summarize_research_paper_parity(report)

    assert report.paper_trade_count == 0
    assert summary["paper_trade_count"] == 0
    assert "No paper or live order is created." in report.safety_notes
    assert (tmp_path / "parity" / "pytest_research_paper_parity.md").exists()
    assert (tmp_path / "parity" / "pytest_research_paper_parity.json").exists()
