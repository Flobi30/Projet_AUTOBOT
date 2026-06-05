import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import main as cli_main
from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.grid_experiment_runner import (
    GRID_EXPERIMENT_FAMILIES,
    GridExperimentConfig,
    build_grid_experiment_variants,
    run_grid_experiments,
)


pytestmark = pytest.mark.integration


def _create_state_db(path: Path, *, symbols=("TRXEUR", "XLMZEUR"), minutes=120) -> Path:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE market_price_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id TEXT,
            symbol TEXT NOT NULL,
            price REAL NOT NULL,
            observed_at TEXT NOT NULL,
            bucket_start TEXT,
            source TEXT,
            created_at TEXT
        )
        """
    )
    start = datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc)
    for symbol in symbols:
        for index in range(minutes):
            timestamp = start + timedelta(minutes=index)
            cycle = index % 20
            base = 100.0 if symbol == "TRXEUR" else 10.0
            price = base * (1.0 + ((cycle - 10) / 1000.0))
            conn.execute(
                """
                INSERT INTO market_price_samples
                (sample_id, symbol, price, observed_at, bucket_start, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{symbol}_{index}",
                    symbol,
                    price,
                    timestamp.isoformat(),
                    timestamp.isoformat(),
                    "pytest",
                    timestamp.isoformat(),
                ),
            )
    conn.commit()
    conn.close()
    return path


def test_build_grid_experiment_variants_is_conservative_and_covers_requested_families():
    variants = build_grid_experiment_variants()
    families = {variant.family for variant in variants}

    assert "baseline_current" in {variant.name for variant in variants}
    assert set(GRID_EXPERIMENT_FAMILIES).issubset(families)
    assert len(variants) < 100


def test_grid_experiment_runner_writes_reports_and_keeps_live_disabled(tmp_path):
    state_db = _create_state_db(tmp_path / "autobot_state.db")
    report = run_grid_experiments(
        GridExperimentConfig(
            run_id="pytest_grid_exp",
            state_db_path=state_db,
            symbols=("TRXEUR", "XLMZEUR"),
            timeframe="1m",
            output_dir=tmp_path / "reports",
            dataset_output_dir=tmp_path / "data",
            max_variants=3,
            min_closed_trades=1,
            candidate_min_closed_trades=100,
            train_window_bars=20,
            test_window_bars=10,
            min_folds=2,
        )
    )

    assert report.json_report_path and Path(report.json_report_path).exists()
    assert report.markdown_report_path and Path(report.markdown_report_path).exists()
    assert report.cost_config["taker_fee_bps"] == 16.0
    assert report.cost_config["fallback_spread_bps"] == 8.0
    assert report.cost_config["slippage_bps"] == 4.0
    assert report.cells
    assert report.best_by_symbol
    assert all(cell.live_promotion_allowed is False for cell in report.cells)
    assert all("live" not in cell.candidate_status for cell in report.cells)
    assert "No live trading permission is granted." in report.safety_notes


def test_grid_experiment_runner_rejects_invalid_parameters(tmp_path):
    state_db = _create_state_db(tmp_path / "autobot_state.db")
    with pytest.raises(ValueError):
        GridExperimentConfig(
            run_id="bad",
            state_db_path=state_db,
            symbols=("TRXEUR",),
            max_variants=0,
        )
    with pytest.raises(ValueError):
        GridExperimentConfig(
            run_id="bad",
            state_db_path=state_db,
            symbols=("TRXEUR",),
            cost_config=ExecutionCostConfig(taker_fee_bps=-1.0),
        )


def test_grid_experiment_cli_runs_research_only(tmp_path):
    state_db = _create_state_db(tmp_path / "autobot_state.db", symbols=("TRXEUR",), minutes=80)
    exit_code = cli_main(
        [
            "grid-experiments",
            "--run-id",
            "pytest_grid_cli",
            "--state-db",
            str(state_db),
            "--symbols",
            "TRXEUR",
            "--timeframe",
            "1m",
            "--output-dir",
            str(tmp_path / "reports"),
            "--dataset-output-dir",
            str(tmp_path / "data"),
            "--max-variants",
            "1",
            "--min-closed-trades",
            "1",
            "--candidate-min-closed-trades",
            "100",
            "--train-window-bars",
            "20",
            "--test-window-bars",
            "10",
            "--min-folds",
            "2",
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "reports" / "pytest_grid_cli.json").exists()
