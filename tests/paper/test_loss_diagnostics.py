import json
import sqlite3
from datetime import datetime, timezone

import pytest

from autobot.v2 import cli
from autobot.v2.paper.loss_diagnostics import (
    PaperLossDiagnosticsConfig,
    _opportunity_scoring_diagnostic,
    build_paper_loss_diagnostics_report,
    segment_paper_capital_block_reason,
)
from autobot.v2.research.trade_journal import TradeRecord


pytestmark = pytest.mark.unit


def _create_state_db(path):
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
                exchange_order_id TEXT,
                decision_id TEXT,
                signal_id TEXT,
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


def _insert_pair(
    conn,
    *,
    strategy="trend_momentum",
    symbol="TRXEUR",
    position_id="p1",
    gross=1.0,
    net=0.5,
    timeframe="5m",
    regime="trend",
    execution_mode="shadow_paper",
    slippage_bps=5.0,
    fee_open=0.1,
    fee_close=0.1,
):
    conn.execute(
        """
        INSERT INTO trade_ledger
        (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
         volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
         strategy_id, timeframe, signal_source, gross_pnl, net_pnl, regime,
         execution_liquidity, execution_mode, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{position_id}_open",
            position_id,
            "inst",
            symbol,
            "buy",
            1.0,
            1.0,
            100.0,
            fee_open,
            slippage_bps,
            None,
            1,
            0,
            strategy,
            timeframe,
            "pytest",
            None,
            None,
            regime,
            "shadow_lab",
            execution_mode,
            "2026-07-01T00:00:00+00:00",
        ),
    )
    conn.execute(
        """
        INSERT INTO trade_ledger
        (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
         volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
         strategy_id, timeframe, signal_source, gross_pnl, net_pnl, regime,
         execution_liquidity, execution_mode, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{position_id}_close",
            position_id,
            "inst",
            symbol,
            "sell",
            1.0,
            1.0,
            100.0,
            fee_close,
            slippage_bps,
            net,
            0,
            1,
            strategy,
            timeframe,
            "pytest",
            gross,
            net,
            regime,
            "shadow_lab",
            execution_mode,
            "2026-07-01T01:00:00+00:00",
        ),
    )


def _write_registry(path):
    payload = {
        "decision_statuses": [
            "learning",
            "candidate",
            "backtest_passed",
            "walk_forward_passed",
            "shadow_passed",
            "paper_validated",
            "rejected",
            "retired_from_execution",
        ],
        "live_auto_promotion_allowed": False,
        "hypotheses": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_loss_diagnostics_uses_only_attributed_shadow_paper_rows(tmp_path):
    db_path = tmp_path / "state.db"
    registry = tmp_path / "registry.json"
    _create_state_db(db_path)
    _write_registry(registry)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="shadow_1", gross=2.0, net=1.0)
        _insert_pair(conn, position_id="paper_1", gross=100.0, net=100.0, execution_mode="paper_capital")
        _insert_pair(conn, position_id="grid_1", strategy="dynamic_grid", gross=100.0, net=100.0)
        _insert_pair(conn, position_id="legacy_1", strategy=None, gross=100.0, net=100.0)

    report = build_paper_loss_diagnostics_report(
        PaperLossDiagnosticsConfig(
            state_db_path=db_path,
            registry_path=registry,
            run_id="pytest_loss",
            min_segment_trades=1,
        ),
        write_report=False,
    ).to_dict()

    trend = next(item for item in report["strategy_diagnostics"] if item["strategy_id"] == "trend_momentum")
    assert trend["summary"]["trade_count"] == 1
    assert trend["summary"]["net_pnl_eur"] == pytest.approx(1.0)
    assert report["execution_mode"] == "shadow_paper"


def test_loss_diagnostics_distinguishes_gross_and_net_pf_and_costs(tmp_path):
    db_path = tmp_path / "state.db"
    registry = tmp_path / "registry.json"
    _create_state_db(db_path)
    _write_registry(registry)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="win", gross=3.0, net=0.5, fee_open=0.6, fee_close=0.6)
        _insert_pair(conn, position_id="loss", gross=-1.0, net=-2.0, fee_open=0.2, fee_close=0.2)

    report = build_paper_loss_diagnostics_report(
        PaperLossDiagnosticsConfig(
            state_db_path=db_path,
            registry_path=registry,
            run_id="pytest_loss",
            min_segment_trades=1,
        ),
        write_report=False,
    ).to_dict()
    trend = next(item for item in report["strategy_diagnostics"] if item["strategy_id"] == "trend_momentum")
    summary = trend["summary"]
    assert summary["gross_profit_factor"] == pytest.approx(3.0)
    assert summary["net_profit_factor"] == pytest.approx(0.25)
    assert summary["fees_eur"] == pytest.approx(1.6)
    assert summary["slippage_eur"] > 0.0
    assert "gross_edge_eroded_by_costs" in summary["reasons"]
    assert trend["policy"]["paper_capital_allowed"] is False


def test_loss_diagnostics_segments_by_pair_timeframe_and_regime(tmp_path):
    db_path = tmp_path / "state.db"
    registry = tmp_path / "registry.json"
    _create_state_db(db_path)
    _write_registry(registry)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="trx", symbol="TRXEUR", timeframe="5m", regime="trend", gross=2, net=1)
        _insert_pair(conn, position_id="xlm", symbol="XLMEUR", timeframe="15m", regime="range", gross=-2, net=-3)

    report = build_paper_loss_diagnostics_report(
        PaperLossDiagnosticsConfig(
            state_db_path=db_path,
            registry_path=registry,
            run_id="pytest_loss",
            min_segment_trades=1,
        ),
        write_report=False,
    ).to_dict()
    table = report["segment_tables"]["by_strategy_symbol_timeframe_regime"]
    keys = [item["key"] for item in table]
    assert {
        "strategy_id": "trend_momentum",
        "symbol": "TRXEUR",
        "timeframe": "5m",
        "regime": "trend",
    } in keys
    assert {
        "strategy_id": "trend_momentum",
        "symbol": "XLMEUR",
        "timeframe": "15m",
        "regime": "range",
    } in keys


def test_disabled_segment_policy_blocks_paper_capital_routing(tmp_path):
    db_path = tmp_path / "state.db"
    registry = tmp_path / "registry.json"
    _create_state_db(db_path)
    _write_registry(registry)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="bad1", symbol="BTCEUR", gross=-1.0, net=-2.0)
        _insert_pair(conn, position_id="bad2", symbol="BTCEUR", gross=-2.0, net=-3.0)

    report = build_paper_loss_diagnostics_report(
        PaperLossDiagnosticsConfig(
            state_db_path=db_path,
            registry_path=registry,
            run_id="pytest_loss",
            min_segment_trades=2,
        ),
        write_report=False,
    )
    trend = next(item for item in report.strategy_diagnostics if item.strategy_id == "trend_momentum")
    disabled = trend.disabled_segment_candidates[0]
    assert disabled.recommendation == "disabled_segment_recommended"
    assert segment_paper_capital_block_reason(disabled) == "disabled_segment"


def test_opportunity_scoring_is_filter_not_alpha_strategy():
    now = datetime(2026, 7, 1, tzinfo=timezone.utc)
    trades = [
        TradeRecord(
            run_id="pytest",
            strategy_id="trend_momentum",
            symbol="TRXEUR",
            side="buy",
            opened_at=now,
            closed_at=now,
            quantity=1.0,
            entry_price=1.0,
            exit_price=1.0,
            gross_pnl_eur=1.0,
            net_pnl_eur=0.8,
            metadata={"opportunity_score": 90, "execution_mode": "shadow_paper"},
        ),
        TradeRecord(
            run_id="pytest",
            strategy_id="trend_momentum",
            symbol="XLMEUR",
            side="buy",
            opened_at=now,
            closed_at=now,
            quantity=1.0,
            entry_price=1.0,
            exit_price=1.0,
            gross_pnl_eur=-1.0,
            net_pnl_eur=-1.2,
            metadata={"opportunity_score": 10, "execution_mode": "shadow_paper"},
        ),
    ]
    diagnostic = _opportunity_scoring_diagnostic(trades, 1_000.0).to_dict()
    assert diagnostic["status"] == "score_filter_analysis_available"
    assert "filter only" in diagnostic["notes"][0].lower()


def test_cli_paper_loss_diagnostics_writes_report(tmp_path, capsys):
    db_path = tmp_path / "state.db"
    registry = tmp_path / "registry.json"
    output_dir = tmp_path / "loss"
    _create_state_db(db_path)
    _write_registry(registry)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="shadow_1", gross=2.0, net=1.0)

    exit_code = cli.main(
        [
            "paper-loss-diagnostics",
            "--state-db",
            str(db_path),
            "--registry-path",
            str(registry),
            "--run-id",
            "pytest_loss",
            "--min-segment-trades",
            "1",
            "--output-dir",
            str(output_dir),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["source"] == "post_p2_shadow_paper_trade_ledger"
    assert (output_dir / "pytest_loss.md").exists()
    persisted = json.loads((output_dir / "pytest_loss.json").read_text(encoding="utf-8"))
    assert persisted["json_report_path"].endswith("pytest_loss.json")
    assert persisted["markdown_report_path"].endswith("pytest_loss.md")
