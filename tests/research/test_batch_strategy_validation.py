import sqlite3

import pytest

from autobot.v2.research.batch_strategy_validation import (
    BatchStrategyValidationConfig,
    infer_default_windows,
    run_batch_strategy_validation,
    write_batch_strategy_validation_report,
)
from autobot.v2.research.execution_cost_model import ExecutionCostConfig


pytestmark = pytest.mark.integration


def _state_db_with_samples(path):
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
        rows = []
        for idx in range(12):
            rows.append(
                (
                    f"sample_{idx}",
                    "TRXEUR",
                    100.0 + (idx % 4) - (idx // 4),
                    f"2026-06-0{1 + idx // 6}T00:{idx % 6:02d}:00+00:00",
                    f"bucket_{idx}",
                    "runtime",
                    f"created_{idx}",
                )
            )
        conn.executemany(
            """
            INSERT INTO market_price_samples
            (sample_id, symbol, price, observed_at, bucket_start, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def test_batch_validation_infers_windows_and_writes_report(tmp_path):
    state_db = tmp_path / "state.db"
    _state_db_with_samples(state_db)

    windows = infer_default_windows(state_db, symbols=("TRXEUR",))
    assert [window.name for window in windows][:3] == ["full", "early", "middle"]

    report = run_batch_strategy_validation(
        BatchStrategyValidationConfig(
            run_id="pytest_batch",
            state_db_path=state_db,
            symbols=("TRXEUR",),
            strategies=("trend",),
            output_dir=tmp_path / "batch",
            min_closed_trades=1,
            cost_config=ExecutionCostConfig(taker_fee_bps=16.0, fallback_spread_bps=8.0, slippage_bps=4.0),
        )
    )
    written = write_batch_strategy_validation_report(report, tmp_path / "batch")

    assert len(report.windows) >= 1
    assert report.status_by_strategy["trend"] in {"research_only", "shadow_candidate"}
    assert report.window_summaries
    assert "No live trading permission is granted." in report.safety_notes
    assert (tmp_path / "batch" / "pytest_batch.md").exists()
    assert (tmp_path / "batch" / "pytest_batch.json").exists()
    assert written.markdown_report_path


def test_batch_validation_runs_from_csv_dataset_research_only(tmp_path):
    csv_path = tmp_path / "ohlcv.csv"
    lines = ["timestamp,symbol,timeframe,open,high,low,close,volume"]
    for idx in range(12):
        lines.append(
            f"2026-06-01T00:{idx:02d}:00+00:00,TRXEUR,1m,"
            f"{100 + idx * 0.1:.4f},{101 + idx * 0.1:.4f},{99 + idx * 0.1:.4f},"
            f"{100 + idx * 0.1:.4f},1000"
        )
    csv_path.write_text("\n".join(lines), encoding="utf-8")

    windows = infer_default_windows(csv_path, symbols=("TRXEUR",), data_source="csv")
    assert windows[0].name == "full"

    report = run_batch_strategy_validation(
        BatchStrategyValidationConfig(
            run_id="pytest_batch_csv",
            symbols=("TRXEUR",),
            data_source="csv",
            data_path=csv_path,
            strategies=("trend",),
            output_dir=tmp_path / "batch_csv",
            min_closed_trades=1,
            cost_config=ExecutionCostConfig(taker_fee_bps=16.0, fallback_spread_bps=8.0, slippage_bps=4.0),
        )
    )

    assert report.data_source == "csv"
    assert report.data_path == str(csv_path)
    assert report.state_db_path == ""
    assert report.status_by_strategy["trend"] in {"research_only", "shadow_candidate"}
    assert "No live trading permission is granted." in report.safety_notes
    assert (tmp_path / "batch_csv" / "pytest_batch_csv.md").exists()
