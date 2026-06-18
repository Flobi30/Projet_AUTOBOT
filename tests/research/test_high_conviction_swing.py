import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import main as cli_main
from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.high_conviction_swing import (
    HighConvictionSwingConfig,
    build_high_conviction_swing_report,
)


pytestmark = pytest.mark.unit


def _create_state_db(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE decision_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT,
            decision_id TEXT,
            signal_id TEXT,
            instance_id TEXT,
            symbol TEXT,
            strategy TEXT,
            engine TEXT,
            event_type TEXT,
            event_status TEXT,
            reason TEXT,
            source TEXT,
            payload_json TEXT,
            created_at TEXT
        )
        """
    )
    connection.execute(
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
    connection.commit()
    connection.close()
    return path


def _insert_decision(
    path: Path,
    *,
    symbol: str,
    timestamp: datetime,
    expected_move_bps: float | None,
    price: float = 100.0,
    reason: str = "cost_guard",
    strategy: str = "grid",
) -> None:
    payload = {
        "side": "buy",
        "price": price,
        "cost_bps": 20.0,
        "min_edge_bps": 30.0,
    }
    if expected_move_bps is not None:
        payload.update(
            {
                "expected_move_bps": expected_move_bps,
                "gross_edge_bps": expected_move_bps,
                "net_edge_bps": expected_move_bps - 20.0,
            }
        )
    connection = sqlite3.connect(path)
    connection.execute(
        """
        INSERT INTO decision_ledger
        (event_id, decision_id, signal_id, instance_id, symbol, strategy, engine,
         event_type, event_status, reason, source, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"event_{symbol}_{timestamp.minute}_{expected_move_bps}",
            None,
            f"sig_{symbol}_{timestamp.minute}_{expected_move_bps}",
            "instance_1",
            symbol,
            strategy,
            strategy,
            "signal",
            "rejected",
            reason,
            "pytest",
            json.dumps(payload),
            timestamp.isoformat(),
        ),
    )
    connection.commit()
    connection.close()


def _insert_price(path: Path, *, symbol: str, timestamp: datetime, price: float) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        INSERT INTO market_price_samples
        (sample_id, symbol, price, observed_at, bucket_start, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{symbol}_{timestamp.isoformat()}",
            symbol,
            price,
            timestamp.isoformat(),
            timestamp.isoformat(),
            "pytest",
            timestamp.isoformat(),
        ),
    )
    connection.commit()
    connection.close()


def test_high_conviction_report_buckets_expected_move_and_keeps_live_disabled(tmp_path):
    db_path = _create_state_db(tmp_path / "state.db")
    start = datetime(2026, 6, 18, 0, 0, tzinfo=timezone.utc)
    _insert_decision(db_path, symbol="TRXEUR", timestamp=start, expected_move_bps=40.0)
    _insert_decision(db_path, symbol="TRXEUR", timestamp=start + timedelta(minutes=1), expected_move_bps=120.0)
    _insert_decision(db_path, symbol="TRXEUR", timestamp=start + timedelta(minutes=2), expected_move_bps=600.0)
    _insert_decision(db_path, symbol="TRXEUR", timestamp=start + timedelta(minutes=3), expected_move_bps=None)
    for minutes, price in ((-60, 99.0), (-15, 99.5), (0, 100.0), (10, 102.0), (20, 103.0)):
        _insert_price(db_path, symbol="TRXEUR", timestamp=start + timedelta(minutes=minutes), price=price)

    report = build_high_conviction_swing_report(
        HighConvictionSwingConfig(
            run_id="pytest_hc_buckets",
            state_db_path=db_path,
            min_expected_move_bps=(100.0,),
            risk_reward_ratios=(2.0,),
            max_hold_hours=(6.0,),
            exit_modes=("fixed_tp_sl",),
            require_mtf_alignment=False,
            cost_config=ExecutionCostConfig(
                taker_fee_bps=0.0,
                maker_fee_bps=0.0,
                fallback_spread_bps=0.0,
                slippage_bps=0.0,
                latency_buffer_bps=0.0,
            ),
        )
    )

    assert report.expected_move_distribution["lt_50_bps"]["count"] == 1
    assert report.expected_move_distribution["100_149_bps"]["count"] == 1
    assert report.expected_move_distribution["400_999_bps"]["count"] == 1
    assert report.expected_move_distribution["unknown"]["count"] == 1
    assert report.live_promotion_allowed is False
    assert "No Kraken order can be created by this command." in report.safety_notes


def test_high_conviction_scenario_filters_micro_signal_and_charges_costs(tmp_path):
    db_path = _create_state_db(tmp_path / "state.db")
    start = datetime(2026, 6, 18, 0, 0, tzinfo=timezone.utc)
    _insert_decision(db_path, symbol="TRXEUR", timestamp=start, expected_move_bps=80.0, price=100.0)
    _insert_decision(db_path, symbol="TRXEUR", timestamp=start + timedelta(minutes=1), expected_move_bps=200.0, price=100.0)
    for minutes, price in ((-60, 99.0), (-15, 99.5), (0, 100.0), (2, 100.8), (10, 102.0)):
        _insert_price(db_path, symbol="TRXEUR", timestamp=start + timedelta(minutes=minutes), price=price)

    report = build_high_conviction_swing_report(
        HighConvictionSwingConfig(
            run_id="pytest_hc_filter",
            state_db_path=db_path,
            min_expected_move_bps=(100.0,),
            risk_reward_ratios=(2.0,),
            max_hold_hours=(6.0,),
            exit_modes=("fixed_tp_sl",),
            require_mtf_alignment=False,
            cost_config=ExecutionCostConfig(
                taker_fee_bps=0.0,
                maker_fee_bps=0.0,
                fallback_spread_bps=0.0,
                slippage_bps=0.0,
                latency_buffer_bps=0.0,
            ),
        )
    )

    scenario = report.scenario_results[0]
    assert scenario.skipped_low_expected_move == 1
    assert scenario.trade_count == 1
    assert scenario.net_return_bps_total == pytest.approx(80.0)
    assert scenario.sample_trades[0]["exit_reason"] == "take_profit"


def test_high_conviction_mtf_alignment_can_block_misaligned_signal(tmp_path):
    db_path = _create_state_db(tmp_path / "state.db")
    start = datetime(2026, 6, 18, 0, 0, tzinfo=timezone.utc)
    _insert_decision(db_path, symbol="TRXEUR", timestamp=start, expected_move_bps=200.0, price=100.0)
    for minutes, price in ((-60, 110.0), (-15, 99.0), (0, 100.0), (10, 103.0)):
        _insert_price(db_path, symbol="TRXEUR", timestamp=start + timedelta(minutes=minutes), price=price)

    report = build_high_conviction_swing_report(
        HighConvictionSwingConfig(
            run_id="pytest_hc_mtf",
            state_db_path=db_path,
            min_expected_move_bps=(100.0,),
            risk_reward_ratios=(2.0,),
            max_hold_hours=(6.0,),
            exit_modes=("fixed_tp_sl",),
            require_mtf_alignment=True,
            cost_config=ExecutionCostConfig(
                taker_fee_bps=0.0,
                maker_fee_bps=0.0,
                fallback_spread_bps=0.0,
                slippage_bps=0.0,
                latency_buffer_bps=0.0,
            ),
        )
    )

    scenario = report.scenario_results[0]
    assert scenario.trade_count == 0
    assert scenario.skipped_mtf_misaligned == 1


def test_high_conviction_cli_writes_reports(tmp_path, capsys):
    db_path = _create_state_db(tmp_path / "state.db")
    start = datetime(2026, 6, 18, 0, 0, tzinfo=timezone.utc)
    _insert_decision(db_path, symbol="TRXEUR", timestamp=start, expected_move_bps=200.0)
    for minutes, price in ((-60, 99.0), (-15, 99.5), (0, 100.0), (10, 103.0)):
        _insert_price(db_path, symbol="TRXEUR", timestamp=start + timedelta(minutes=minutes), price=price)

    exit_code = cli_main(
        [
            "high-conviction-swing",
            "--run-id",
            "pytest_hc_cli",
            "--state-db",
            str(db_path),
            "--symbols",
            "TRXEUR",
            "--min-expected-move-bps",
            "100,200",
            "--risk-reward-ratios",
            "2",
            "--max-hold-hours",
            "6",
            "--exit-modes",
            "fixed_tp_sl",
            "--no-mtf-required",
            "--output-dir",
            str(tmp_path / "reports"),
            "--cost-profile",
            "paper_current_taker",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["live_promotion_allowed"] is False
    assert output["cost_config"]["cost_profile"] == "paper_current_taker"
    assert (tmp_path / "reports" / "pytest_hc_cli.json").exists()
    assert (tmp_path / "reports" / "pytest_hc_cli.md").exists()
