import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import main as cli_main
from autobot.v2.research.high_conviction_walk_forward import (
    HighConvictionWalkForwardConfig,
    _fold_windows,
    build_high_conviction_walk_forward_report,
    write_high_conviction_walk_forward_report,
)


pytestmark = pytest.mark.unit


def _write(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _bar(timestamp: datetime, timeframe: str, price: float, spread: float) -> dict[str, object]:
    return {
        "timestamp": timestamp.isoformat(),
        "symbol": "TRXEUR",
        "timeframe": timeframe,
        "open": f"{price:.8f}",
        "high": f"{price + spread:.8f}",
        "low": f"{max(0.01, price - spread):.8f}",
        "close": f"{price:.8f}",
        "volume": "1000",
    }


def _dataset(tmp_path: Path) -> tuple[Path, Path, Path]:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    hourly = [_bar(start + timedelta(hours=index), "1h", 96.0 + index * 0.28, 0.55) for index in range(36)]
    fifteen = []
    for index in range(120):
        if index < 70:
            price = 98.0 + index * 0.035
        elif index < 82:
            price = 101.0 + (index - 70) * 0.38
        else:
            price = 105.5 + (index - 82) * 0.08
        fifteen.append(_bar(start + timedelta(minutes=15 * index), "15m", price, 0.35))
    five = []
    for index in range(420):
        if index < 210:
            price = 98.0 + index * 0.012
        elif index < 270:
            price = 101.0 + (index - 210) * 0.12
        else:
            price = 108.2 + (index - 270) * 0.03
        five.append(_bar(start + timedelta(minutes=5 * index), "5m", price, 0.20))
    return (
        _write(tmp_path / "trx_5m.csv", five),
        _write(tmp_path / "trx_15m.csv", fifteen),
        _write(tmp_path / "trx_1h.csv", hourly),
    )


def _config(tmp_path: Path, paths: tuple[Path, ...]) -> HighConvictionWalkForwardConfig:
    return HighConvictionWalkForwardConfig(
        run_id="pytest_high_conviction_walk_forward",
        data_paths=paths,
        symbols=("TRXEUR",),
        min_expected_move_bps=200.0,
        risk_reward_ratio=2.0,
        max_hold_hours=2.0,
        train_window_bars=48,
        test_window_bars=24,
        step_window_bars=24,
        min_folds=3,
        output_dir=tmp_path / "reports",
    )


def test_walk_forward_deduplicates_bars_and_remains_research_only(tmp_path):
    paths = _dataset(tmp_path)
    duplicate_five = tmp_path / "trx_5m_duplicate.csv"
    duplicate_five.write_text(paths[0].read_text(encoding="utf-8"), encoding="utf-8")
    report = build_high_conviction_walk_forward_report(_config(tmp_path, paths + (duplicate_five,)))

    assert report.fold_count == 3
    assert report.duplicate_bar_count > 0
    assert report.decision.paper_candidate_allowed is False
    assert report.decision.live_promotion_allowed is False
    assert report.primary_aggregate is not None
    assert {row.cost_profile for row in report.aggregates} == {"paper_current_taker", "research_stress"}
    assert {row.policy for row in report.aggregates} == {"conservative", "dynamic_scaling"}

    written = write_high_conviction_walk_forward_report(report, tmp_path / "reports")
    assert written.json_report_path
    assert written.markdown_report_path
    assert Path(written.json_report_path).exists()
    assert Path(written.markdown_report_path).exists()


def test_walk_forward_never_uses_entries_outside_the_test_window(tmp_path):
    report = build_high_conviction_walk_forward_report(_config(tmp_path, _dataset(tmp_path)))

    for fold in report.folds:
        start = datetime.fromisoformat(fold.test_start_at)
        end = datetime.fromisoformat(fold.test_end_at)
        for trade in fold.portfolio.trade_records:
            assert trade.opened_at >= start
            assert trade.closed_at <= end


def test_walk_forward_requires_fifty_closed_trades_for_review(tmp_path):
    paths = _dataset(tmp_path)
    with pytest.raises(ValueError, match="at least 50 closed trades"):
        HighConvictionWalkForwardConfig(
            run_id="invalid",
            data_paths=paths,
            min_closed_trades_for_review=49,
        )


def test_fold_windows_are_chronological_and_non_overlapping_by_default(tmp_path):
    config = _config(tmp_path, _dataset(tmp_path))
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    timeline = [start + timedelta(minutes=15 * index) for index in range(120)]

    windows = _fold_windows(config, timeline)

    assert len(windows) == 3
    assert all(train_start <= train_end < test_start <= test_end for train_start, train_end, test_start, test_end in windows)
    assert windows[0][3] < windows[1][2]


def test_walk_forward_cli_writes_research_only_report(tmp_path, capsys):
    paths = _dataset(tmp_path)

    exit_code = cli_main(
        [
            "high-conviction-walk-forward",
            "--run-id",
            "pytest_high_conviction_walk_forward_cli",
            "--data-paths",
            ",".join(str(path) for path in paths),
            "--symbols",
            "TRXEUR",
            "--min-expected-move-bps",
            "200",
            "--max-hold-hours",
            "2",
            "--train-window-bars",
            "48",
            "--test-window-bars",
            "24",
            "--step-window-bars",
            "24",
            "--min-folds",
            "3",
            "--output-dir",
            str(tmp_path / "cli_reports"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["decision"]["paper_candidate_allowed"] is False
    assert payload["live_promotion_allowed"] is False
    assert (tmp_path / "cli_reports" / "pytest_high_conviction_walk_forward_cli.json").exists()
