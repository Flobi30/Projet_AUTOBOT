import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import main as cli_main
from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.strategy_experiment_runner import (
    StrategyExperimentConfig,
    build_strategy_experiment_variants,
    run_strategy_experiments,
)


pytestmark = pytest.mark.integration


def _create_state_db(path: Path, *, symbols=("TRXEUR", "XLMZEUR"), minutes=160) -> Path:
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
    start = datetime(2026, 6, 6, 0, 0, tzinfo=timezone.utc)
    for symbol in symbols:
        for index in range(minutes):
            timestamp = start + timedelta(minutes=index)
            drift = (index / max(minutes, 1)) * 0.01
            cycle = (index % 18) - 9
            base = 100.0 if symbol == "TRXEUR" else 10.0
            price = base * (1.0 + drift + (cycle / 1200.0))
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


def test_strategy_experiment_variants_cover_trend_and_mean_reversion():
    variants = build_strategy_experiment_variants()
    strategies = {variant.strategy for variant in variants}
    names = {(variant.strategy, variant.name) for variant in variants}

    assert strategies == {"trend", "mean_reversion"}
    assert ("trend", "baseline_current") in names
    assert ("mean_reversion", "baseline_current") in names
    assert len(variants) < 40


def test_strategy_experiment_runner_writes_reports_and_keeps_live_disabled(tmp_path):
    state_db = _create_state_db(tmp_path / "autobot_state.db")
    report = run_strategy_experiments(
        StrategyExperimentConfig(
            run_id="pytest_strategy_exp",
            state_db_path=state_db,
            symbols=("TRXEUR", "XLMZEUR"),
            strategies=("trend", "mean_reversion"),
            timeframe="1m",
            output_dir=tmp_path / "reports",
            dataset_output_dir=tmp_path / "data",
            max_variants_per_strategy=2,
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
    assert report.best_by_strategy_symbol
    assert all(cell.live_promotion_allowed is False for cell in report.cells)
    assert all("live" not in cell.candidate_status for cell in report.cells)
    assert "No live trading permission is granted." in report.safety_notes


def test_strategy_experiment_runner_rejects_invalid_parameters(tmp_path):
    state_db = _create_state_db(tmp_path / "autobot_state.db")
    with pytest.raises(ValueError):
        StrategyExperimentConfig(
            run_id="bad",
            state_db_path=state_db,
            symbols=("TRXEUR",),
            strategies=("grid",),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError):
        StrategyExperimentConfig(
            run_id="bad",
            state_db_path=state_db,
            symbols=("TRXEUR",),
            cost_config=ExecutionCostConfig(slippage_bps=-1.0),
        )


def test_strategy_experiment_cli_runs_research_only(tmp_path):
    state_db = _create_state_db(tmp_path / "autobot_state.db", symbols=("TRXEUR",), minutes=90)
    exit_code = cli_main(
        [
            "strategy-experiments",
            "--run-id",
            "pytest_strategy_cli",
            "--state-db",
            str(state_db),
            "--symbols",
            "TRXEUR",
            "--strategies",
            "trend",
            "--timeframe",
            "1m",
            "--output-dir",
            str(tmp_path / "reports"),
            "--dataset-output-dir",
            str(tmp_path / "data"),
            "--max-variants-per-strategy",
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
    assert (tmp_path / "reports" / "pytest_strategy_cli.json").exists()
