import json
import sqlite3

import pytest

from autobot.v2 import cli
from autobot.v2.paper.db_integrity import DbIntegrityConfig, build_db_integrity_report
from autobot.v2.paper.paper_confidence import PaperConfidenceConfig, build_paper_confidence_report
from autobot.v2.paper.score_filter_simulation import (
    ScoreFilterSimulationConfig,
    build_score_filter_simulation_report,
)


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
    position_id,
    strategy="trend_momentum",
    symbol="TRXEUR",
    net=1.0,
    gross=None,
    score=None,
    score_bucket=None,
    execution_mode="shadow_paper",
    fee=0.1,
    slippage_bps=1.0,
):
    metadata = {}
    if score is not None:
        metadata["opportunity_score"] = score
    if score_bucket is not None:
        metadata["score_bucket"] = score_bucket
    encoded_metadata = json.dumps(metadata) if metadata else None
    gross = net + (2 * fee) if gross is None else gross
    rows = [
        (
            f"{position_id}-open",
            position_id,
            "inst",
            symbol,
            "buy",
            1.0,
            1.0,
            10.0,
            fee,
            slippage_bps,
            None,
            1,
            0,
            encoded_metadata,
            None,
            strategy,
            "5m",
            "pytest",
            None,
            None,
            "trend",
            "shadow_lab",
            execution_mode,
            "2026-07-03T00:00:00+00:00",
        ),
        (
            f"{position_id}-close",
            position_id,
            "inst",
            symbol,
            "sell",
            1.0,
            1.0,
            10.0,
            fee,
            slippage_bps,
            net,
            0,
            1,
            encoded_metadata,
            None,
            strategy,
            "5m",
            "pytest",
            gross,
            net,
            "trend",
            "shadow_lab",
            execution_mode,
            "2026-07-03T00:05:00+00:00",
        ),
    ]
    conn.executemany(
        """
        INSERT INTO trade_ledger
        (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
         volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
         decision_id, signal_id, strategy_id, timeframe, signal_source, gross_pnl, net_pnl,
         regime, execution_liquidity, execution_mode, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def test_score_filter_simulation_is_read_only_and_keeps_buckets_separate(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="high", net=2.0, score=90)
        _insert_pair(conn, position_id="medium", net=1.0, score=55)
        _insert_pair(conn, position_id="low", net=-1.0, score=20)
        _insert_pair(conn, position_id="missing", net=-0.5)
        _insert_pair(conn, position_id="grid", strategy="dynamic_grid", net=99.0, score=95)
        before = conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0]

    report = build_score_filter_simulation_report(
        ScoreFilterSimulationConfig(state_db_path=db_path, run_id="pytest_score", write_report=False)
    ).to_dict()

    with sqlite3.connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0]

    assert before == after
    assert report["bucket_counts"] == {"high": 1, "medium": 1, "low": 1, "missing": 1}
    scenarios = {item["name"]: item for item in report["scenarios"]}
    assert scenarios["all_scored"]["trade_count"] == 3
    assert scenarios["missing_separate"]["trade_count"] == 1
    assert scenarios["low_separate"]["trade_count"] == 1
    assert scenarios["high_only"]["promotable"] is False


def test_paper_confidence_blocks_low_sample_and_shadow_evidence(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        for index in range(10):
            _insert_pair(conn, position_id=f"t{index}", net=1.0, score=80)

    report = build_paper_confidence_report(
        PaperConfidenceConfig(
            state_db_path=db_path,
            strategy_id="trend_momentum",
            run_id="pytest_confidence",
            bootstrap_iterations=50,
            write_report=False,
        )
    ).to_dict()

    assert report["confidence_level"] == "insufficient_data"
    assert report["promotable"] is False
    assert "insufficient_sample_size" in report["blockers"]
    assert "paper_capital_evidence_absent" in report["blockers"]


def test_paper_confidence_never_promotes_positive_shadow_sample(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        for index in range(60):
            _insert_pair(conn, position_id=f"pos{index}", net=1.0, score=80)

    report = build_paper_confidence_report(
        PaperConfidenceConfig(
            state_db_path=db_path,
            strategy_id="trend_momentum",
            run_id="pytest_shadow_confidence",
            bootstrap_iterations=50,
            write_report=False,
        )
    ).to_dict()

    assert report["confidence_level"] == "early_signal"
    assert report["promotable"] is False
    assert "paper_capital_evidence_absent" in report["blockers"]


def test_db_integrity_reports_snapshot_and_invalid_rows(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="bad-bucket", net=1.0, score_bucket="very_high")
        _insert_pair(conn, position_id="negative-cost", net=1.0, fee=-0.1)
        conn.execute(
            "INSERT INTO trade_ledger (trade_id, position_id, instance_id, symbol, side, executed_price, volume, "
            "fees, is_closing_leg, strategy_id, execution_mode, created_at) "
            "VALUES ('dup', 'p1', 'inst', 'TRXEUR', 'sell', 1, 1, 0, 1, 'trend_momentum', 'shadow_paper', '2026-07-03')"
        )
        conn.execute(
            "INSERT INTO trade_ledger (trade_id, position_id, instance_id, symbol, side, executed_price, volume, "
            "fees, is_closing_leg, strategy_id, execution_mode, created_at) "
            "VALUES ('dup', 'p2', 'inst', 'TRXEUR', 'sell', 1, 1, 0, 1, 'trend_momentum', 'shadow_paper', '2026-07-03')"
        )

    report = build_db_integrity_report(
        DbIntegrityConfig(
            state_db_path=db_path,
            snapshot_dir=tmp_path / "snapshots",
            run_id="pytest_integrity",
            write_report=False,
        )
    ).to_dict()

    assert report["source_mode"] == "snapshot"
    assert report["status"] == "FAIL"
    assert report["checks"]["duplicate_trade_id_groups"] == 1
    assert report["checks"]["negative_cost_rows"] >= 1
    assert report["checks"]["invalid_score_bucket_rows"] == 1
    assert report["checks"]["legacy_rows_used_by_official_metrics"] is False


def test_new_p6_cli_commands_are_read_only(tmp_path, capsys):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_pair(conn, position_id="high", net=2.0, score=90)
        row_count = conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0]

    assert cli.main(["score-filter-simulation", "--state-db", str(db_path), "--no-write-report"]) == 0
    score_payload = json.loads(capsys.readouterr().out)
    assert score_payload["scenarios"][0]["promotable"] is False

    assert cli.main([
        "paper-confidence",
        "--state-db",
        str(db_path),
        "--strategy-id",
        "trend_momentum",
        "--bootstrap-iterations",
        "20",
        "--no-write-report",
    ]) == 0
    confidence_payload = json.loads(capsys.readouterr().out)
    assert confidence_payload["promotable"] is False

    assert cli.main(["check-db-integrity", "--state-db", str(db_path), "--no-write-report"]) == 0
    integrity_payload = json.loads(capsys.readouterr().out)
    assert integrity_payload["checks"]["legacy_rows_used_by_official_metrics"] is False

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM trade_ledger").fetchone()[0] == row_count
