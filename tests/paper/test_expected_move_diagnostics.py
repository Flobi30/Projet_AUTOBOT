import json
import sqlite3
from pathlib import Path

import pytest

from autobot.v2.paper.expected_move_diagnostics import (
    ExpectedMoveDiagnosticsConfig,
    build_expected_move_diagnostics,
    write_expected_move_diagnostics,
)


pytestmark = pytest.mark.unit


def _insert_shadow_pair(
    conn: sqlite3.Connection,
    *,
    position_id: str,
    strategy_id: str,
    symbol: str = "BCHEUR",
    net_pnl: float = -1.0,
    expected_move_bps: float | None = 0.0,
    estimated_total_cost_bps: float = 15.0,
    estimated_net_edge_bps: float = -15.0,
    opened_at: str = "2026-07-08T01:00:00+00:00",
    closed_at: str = "2026-07-08T02:00:00+00:00",
) -> None:
    metadata = {
        "execution_mode": "shadow_paper",
        "research_only": True,
        "score_bucket": "low",
        "score_v2_bucket": "low",
        "score_v2_promotable": False,
        "score_v2_paper_capital_allowed": False,
        "score_v2_live_allowed": False,
        "estimated_total_cost_bps": estimated_total_cost_bps,
        "estimated_net_edge_bps": estimated_net_edge_bps,
    }
    if expected_move_bps is not None:
        metadata["expected_move_bps"] = expected_move_bps
    encoded = json.dumps(metadata, sort_keys=True)
    rows = [
        (
            f"{position_id}:open",
            position_id,
            "shadow_paper",
            symbol,
            "buy",
            1.0,
            1.0,
            100.0,
            0.25,
            1.0,
            None,
            1,
            0,
            encoded,
            strategy_id,
            "5m",
            "pytest_shadow",
            None,
            None,
            "trend",
            "shadow_lab",
            "shadow_paper",
            opened_at,
        ),
        (
            f"{position_id}:close",
            position_id,
            "shadow_paper",
            symbol,
            "sell",
            1.0,
            1.0,
            100.0,
            0.25,
            1.0,
            net_pnl,
            0,
            1,
            encoded,
            strategy_id,
            "5m",
            "pytest_shadow",
            net_pnl + 0.5,
            net_pnl,
            "trend",
            "shadow_lab",
            "shadow_paper",
            closed_at,
        ),
    ]
    conn.executemany(
        """
        INSERT INTO trade_ledger
        (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
         volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
         decision_id, strategy_id, timeframe, signal_source, gross_pnl, net_pnl,
         regime, execution_liquidity, execution_mode, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _create_state_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE trade_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT NOT NULL,
                position_id TEXT,
                instance_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                expected_price REAL,
                executed_price REAL NOT NULL,
                volume REAL NOT NULL,
                fees REAL DEFAULT 0,
                slippage_bps REAL,
                realized_pnl REAL,
                is_opening_leg INTEGER DEFAULT 0,
                is_closing_leg INTEGER DEFAULT 0,
                decision_id TEXT,
                strategy_id TEXT,
                timeframe TEXT,
                signal_source TEXT,
                gross_pnl REAL,
                net_pnl REAL,
                regime TEXT,
                execution_liquidity TEXT,
                execution_mode TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def test_expected_move_diagnostics_reports_zero_expected_move_and_high_conviction_missing_paths(tmp_path):
    state_db = tmp_path / "state.db"
    _create_state_db(state_db)
    with sqlite3.connect(state_db) as conn:
        _insert_shadow_pair(
            conn,
            position_id="trend_zero",
            strategy_id="trend_momentum",
            expected_move_bps=0.0,
            estimated_total_cost_bps=15.0,
            estimated_net_edge_bps=-15.0,
            net_pnl=-1.25,
        )

    report = build_expected_move_diagnostics(
        ExpectedMoveDiagnosticsConfig(
            state_db_path=state_db,
            run_id="pytest_expected_move",
            write_report=False,
        )
    )

    trend = report["by_strategy"]["trend_momentum"]
    assert report["safety"]["live_allowed"] is False
    assert report["safety"]["paper_capital_allowed"] is False
    assert report["safety"]["promotable"] is False
    assert report["safety"]["uses_future_data_for_expected_move"] is False
    assert trend["trade_count"] == 1
    assert trend["expected_move_bps"]["max"] == pytest.approx(0.0)
    assert trend["estimated_net_edge_bps"]["median"] == pytest.approx(-15.0)
    assert trend["decision"] == "needs_rework"
    assert trend["decision_reason"] == "expected_move_zero_pretrade"
    assert report["high_conviction"]["diagnosis"] == "high_conviction_data_paths_missing"


def test_expected_move_diagnostics_writes_json_and_markdown_read_only(tmp_path):
    state_db = tmp_path / "state.db"
    output_dir = tmp_path / "reports"
    _create_state_db(state_db)
    with sqlite3.connect(state_db) as conn:
        _insert_shadow_pair(
            conn,
            position_id="mean_positive",
            strategy_id="mean_reversion",
            symbol="LINKEUR",
            expected_move_bps=120.0,
            estimated_total_cost_bps=30.0,
            estimated_net_edge_bps=90.0,
            net_pnl=2.0,
        )
        before = conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0]

    report = build_expected_move_diagnostics(
        ExpectedMoveDiagnosticsConfig(
            state_db_path=state_db,
            output_dir=output_dir,
            run_id="pytest_expected_move_write",
            write_report=True,
        )
    )
    json_path, md_path = write_expected_move_diagnostics(report, output_dir)

    assert json_path.exists()
    assert md_path.exists()
    assert "Expected Move Diagnostics" in md_path.read_text(encoding="utf-8")
    with sqlite3.connect(state_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0] == before
