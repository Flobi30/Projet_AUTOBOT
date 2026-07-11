from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research.data_capability_scanner import (
    build_data_capability_scan_report,
    write_data_capability_scan_report,
)


pytestmark = pytest.mark.unit


def test_data_capability_scanner_detects_existing_ohlcv(tmp_path):
    data_dir = _write_ohlcv(tmp_path)

    report = build_data_capability_scan_report(
        run_id="pytest_capability",
        data_roots=(data_dir,),
        state_db=None,
        memory_path=tmp_path / "missing_memory.json",
    )
    by_id = {item.capability_id: item for item in report.capabilities}

    assert by_id["spot_ohlcv"].available is True
    assert by_id["multi_symbol_ohlcv"].available is True
    assert set(by_id["spot_ohlcv"].symbols) == {"ADAEUR", "BCHEUR"}
    assert {"5m", "15m", "1h"}.issubset(set(by_id["spot_ohlcv"].timeframes))
    assert "volatility_breakout" in by_id["spot_ohlcv"].alpha_families_unlocked
    assert report.paper_capital_allowed is False
    assert report.live_allowed is False
    assert report.promotable is False


def test_funding_and_liquidation_stay_data_missing_without_feeds(tmp_path):
    data_dir = _write_ohlcv(tmp_path)

    report = build_data_capability_scan_report(
        run_id="pytest_missing_derivatives",
        data_roots=(data_dir,),
        memory_path=tmp_path / "missing_memory.json",
    )

    funding = report.alpha_family_status["funding_basis"]
    liquidation = report.alpha_family_status["liquidation_cascade"]
    assert funding["status"] == "DATA_MISSING"
    assert "funding_rates_missing" in funding["blockers"]
    assert "spot_perp_basis_missing" in funding["blockers"]
    assert liquidation["status"] == "DATA_MISSING"
    assert "liquidation_events_missing" in liquidation["blockers"]


def test_scanner_exposes_canonical_snapshot_scheduler_state(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest = {
        "snapshot_id": "ohlcv_test",
        "fingerprint": "abc123",
        "canonical_row_count": 10,
        "duplicate_count": 0,
        "new_data_significance": "same_data",
        "end_at": "2026-01-01T00:00:00+00:00",
    }
    (manifest_dir / "pytest_canonical_ohlcv.json").write_text(json.dumps(manifest), encoding="utf-8")

    report = build_data_capability_scan_report(
        run_id="pytest_canonical_state",
        data_roots=(data_dir, manifest_dir),
        memory_path=tmp_path / "missing_memory.json",
    )

    state = report.scheduler_data_state
    assert state["canonical_ohlcv_ready"] is True
    assert state["snapshot_id"] == "ohlcv_test"
    assert state["new_data_significance"] == "same_data"
    assert state["funding_data_ready"] is False
    assert state["liquidation_data_ready"] is False
    assert "funding_basis" in state["hypotheses_still_blocked"]


def test_scanner_keeps_liquidation_missing_when_derivatives_manifest_lacks_events(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    derivatives_manifest = {
        "snapshot_id": "kraken_futures_test",
        "fingerprint": "abc123",
        "mappings": [{"futures_symbol": "PF_XBTUSD", "base_asset": "BTC"}],
        "funding_history_ready": True,
        "basis_current_ready": True,
        "basis_history_ready": False,
        "current_open_interest_ready": True,
        "open_interest_history_ready": False,
        "predicted_funding_ready": True,
        "mark_candles_ready": True,
        "trade_candles_ready": True,
        "derivatives_data_quality": "smoke_ready_current_basis_only",
        "datasets": [
            {
                "dataset_id": "funding_rates",
                "row_count": 2,
                "start_at": "2026-01-01T00:00:00+00:00",
                "end_at": "2026-01-01T01:00:00+00:00",
                "csv_path": str(tmp_path / "funding.csv"),
            },
            {
                "dataset_id": "basis",
                "row_count": 1,
                "csv_path": str(tmp_path / "basis.csv"),
            },
            {
                "dataset_id": "ticker_snapshots",
                "row_count": 1,
                "csv_path": str(tmp_path / "tickers.csv"),
            },
        ],
    }
    (manifest_dir / "pytest_kraken_futures_derivatives.json").write_text(json.dumps(derivatives_manifest), encoding="utf-8")

    report = build_data_capability_scan_report(
        run_id="pytest_derivatives_manifest",
        data_roots=(data_dir, manifest_dir),
        memory_path=tmp_path / "missing_memory.json",
    )

    state = report.scheduler_data_state
    assert state["funding_history_ready"] is True
    assert state["basis_history_ready"] is False
    assert state["current_open_interest_ready"] is True
    assert state["open_interest_history_ready"] is False
    assert state["liquidation_data_ready"] is False
    assert report.alpha_family_status["funding_basis"]["status"] == "WAITING_FOR_MORE_DATA"
    assert report.alpha_family_status["liquidation_cascade"]["status"] == "DATA_MISSING"


def test_rejected_hypotheses_are_not_retestable_without_new_data(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    memory_path = tmp_path / "memory.json"
    memory_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "hypothesis_id": "volatility_breakout",
                        "alpha_family_id": "volatility_breakout",
                        "final_status": "REJECTED",
                        "related_rejected_hypotheses": ["volatility_breakout"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = build_data_capability_scan_report(
        run_id="pytest_rejected",
        data_roots=(data_dir,),
        memory_path=memory_path,
    )

    rejected = report.rejected_family_status["volatility_breakout"]
    assert rejected["status"] == "REJECTED_CURRENT_CONFIG"
    assert rejected["retest_allowed"] is False
    assert rejected["reason"] == "blocked_until_new_data_signature_or_new_template"


def test_scanner_writes_json_and_markdown_with_storage_policy(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    report = build_data_capability_scan_report(
        run_id="pytest_write",
        data_roots=(data_dir,),
        memory_path=tmp_path / "missing_memory.json",
    )

    written = write_data_capability_scan_report(report, tmp_path / "reports")
    markdown = Path(str(written.markdown_report_path)).read_text(encoding="utf-8")

    assert Path(str(written.json_report_path)).exists()
    assert "Research Storage Policy" in markdown
    assert "data/autobot_state.db" in markdown
    assert "No live trading" in markdown


def test_data_capability_cli_is_registered():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "data-capability-scan",
            "--state-db",
            "data/autobot_state.db",
            "--data-roots",
            "data/research,reports/research",
        ]
    )

    assert args.command == "data-capability-scan"
    assert args.memory_path == "data/research/alpha_research_memory.sqlite3"


def _write_ohlcv(tmp_path: Path) -> Path:
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for symbol in ("BCHEUR", "ADAEUR"):
        _write_rows(data_dir / f"{symbol}_1h.csv", symbol, "1h", start, 20, timedelta(hours=1))
        _write_rows(data_dir / f"{symbol}_15m.csv", symbol, "15m", start, 80, timedelta(minutes=15))
        _write_rows(data_dir / f"{symbol}_5m.csv", symbol, "5m", start, 240, timedelta(minutes=5))
    return data_dir


def _write_rows(path: Path, symbol: str, timeframe: str, start: datetime, count: int, step: timedelta) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume", "symbol", "timeframe"],
        )
        writer.writeheader()
        for index in range(count):
            price = 100 + index
            writer.writerow(
                {
                    "timestamp": (start + index * step).isoformat(),
                    "open": price,
                    "high": price + 1,
                    "low": price - 1,
                    "close": price + 0.5,
                    "volume": 1000,
                    "symbol": symbol,
                    "timeframe": timeframe,
                }
            )
