import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import main as cli_main
from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.high_conviction_discovery import (
    HighConvictionDiscoveryConfig,
    build_high_conviction_discovery_report,
)


pytestmark = pytest.mark.unit


def _write_ohlcv(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _bar(timestamp: datetime, symbol: str, timeframe: str, price: float, *, spread: float = 0.40) -> dict[str, object]:
    return {
        "timestamp": timestamp.isoformat(),
        "symbol": symbol,
        "timeframe": timeframe,
        "open": f"{price:.8f}",
        "high": f"{price + spread:.8f}",
        "low": f"{max(0.01, price - spread):.8f}",
        "close": f"{price:.8f}",
        "volume": "1000",
    }


def _synthetic_multitimeframe_dataset(tmp_path: Path) -> tuple[Path, Path, Path]:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    rows_1h: list[dict[str, object]] = []
    for index in range(36):
        price = 96.0 + index * 0.28
        rows_1h.append(_bar(start + timedelta(hours=index), "TRXEUR", "1h", price, spread=0.55))

    rows_15m: list[dict[str, object]] = []
    for index in range(120):
        timestamp = start + timedelta(minutes=15 * index)
        if index < 70:
            price = 98.0 + index * 0.035
        elif index < 82:
            price = 101.0 + (index - 70) * 0.38
        else:
            price = 105.5 + (index - 82) * 0.08
        rows_15m.append(_bar(timestamp, "TRXEUR", "15m", price, spread=0.35))

    rows_5m: list[dict[str, object]] = []
    for index in range(420):
        timestamp = start + timedelta(minutes=5 * index)
        if index < 210:
            price = 98.0 + index * 0.012
        elif index < 270:
            price = 101.0 + (index - 210) * 0.12
        else:
            price = 108.2 + (index - 270) * 0.03
        rows_5m.append(_bar(timestamp, "TRXEUR", "5m", price, spread=0.20))

    return (
        _write_ohlcv(tmp_path / "trx_5m.csv", rows_5m),
        _write_ohlcv(tmp_path / "trx_15m.csv", rows_15m),
        _write_ohlcv(tmp_path / "trx_1h.csv", rows_1h),
    )


def test_discovery_finds_ohlcv_breakout_without_decision_ledger(tmp_path):
    data_paths = _synthetic_multitimeframe_dataset(tmp_path)
    report = build_high_conviction_discovery_report(
        HighConvictionDiscoveryConfig(
            run_id="pytest_discovery",
            data_paths=data_paths,
            symbols=("TRXEUR",),
            setup_families=("breakout_1h_4h", "trend_continuation"),
            min_expected_move_bps=(200.0,),
            risk_reward_ratios=(2.0,),
            max_hold_hours=(24.0,),
            exit_modes=("fixed_tp_sl",),
            cost_config=ExecutionCostConfig(
                taker_fee_bps=0.0,
                maker_fee_bps=0.0,
                fallback_spread_bps=0.0,
                slippage_bps=0.0,
                latency_buffer_bps=0.0,
            ),
        )
    )

    assert report.setup_count > 0
    assert report.setup_count_by_family["breakout_1h_4h"] > 0
    assert report.expected_move_distribution["200_499_bps"] + report.expected_move_distribution["500_999_bps"] > 0
    assert report.scenario_results[0].trade_count > 0
    assert report.live_promotion_allowed is False
    assert "No Kraken order can be created by this command." in report.safety_notes


def test_discovery_strict_expected_move_threshold_skips_smaller_setups(tmp_path):
    data_paths = _synthetic_multitimeframe_dataset(tmp_path)
    report = build_high_conviction_discovery_report(
        HighConvictionDiscoveryConfig(
            run_id="pytest_discovery_threshold",
            data_paths=data_paths,
            symbols=("TRXEUR",),
            setup_families=("breakout_1h_4h",),
            min_expected_move_bps=(1000.0,),
            risk_reward_ratios=(2.0,),
            max_hold_hours=(24.0,),
            exit_modes=("fixed_tp_sl",),
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
    assert scenario.evaluated_setups == report.setup_count
    assert scenario.skipped_expected_move >= 0
    assert scenario.live_promotion_allowed is False


def test_discovery_cli_writes_reports_and_micro_comparison(tmp_path, capsys):
    data_paths = _synthetic_multitimeframe_dataset(tmp_path)
    micro_report = tmp_path / "micro.json"
    micro_report.write_text(
        json.dumps(
            {
                "conclusion": "micro_trade_bias_detected_no_candidate_yet",
                "best_scenario": {"net_pnl_eur": -12.5, "profit_factor": 0.4, "trade_count": 10},
            }
        ),
        encoding="utf-8",
    )

    exit_code = cli_main(
        [
            "high-conviction-discovery",
            "--run-id",
            "pytest_discovery_cli",
            "--data-paths",
            ",".join(str(path) for path in data_paths),
            "--symbols",
            "TRXEUR",
            "--setup-families",
            "breakout_1h_4h,trend_continuation",
            "--min-expected-move-bps",
            "200",
            "--risk-reward-ratios",
            "2",
            "--max-hold-hours",
            "24",
            "--exit-modes",
            "fixed_tp_sl",
            "--micro-report-json",
            str(micro_report),
            "--output-dir",
            str(tmp_path / "reports"),
            "--cost-profile",
            "research_legacy",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["live_promotion_allowed"] is False
    assert output["grid_micro_comparison"]["micro_report_loaded"] is True
    assert (tmp_path / "reports" / "pytest_discovery_cli.json").exists()
    assert (tmp_path / "reports" / "pytest_discovery_cli.md").exists()

