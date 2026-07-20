from __future__ import annotations

import ast
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2 import cli
from autobot.v2.research.canonical_microstructure_profile import (
    CanonicalMicrostructureProfileConfig,
    build_canonical_microstructure_profile,
    write_canonical_microstructure_profile_report,
)


pytestmark = pytest.mark.unit


def _row(
    *,
    source_id: str,
    event_time: datetime,
    bid: float = 100.0,
    ask: float = 100.2,
    symbol: str = "BTCEUR",
    quote_asset: str = "EUR",
    **overrides: str,
) -> dict[str, str]:
    available = event_time + timedelta(seconds=1)
    ingestion = event_time + timedelta(seconds=2)
    mid = (bid + ask) / 2.0
    row = {
        "schema_version": "1",
        "exchange": "kraken",
        "market_type": "spot",
        "symbol": symbol,
        "base_asset": symbol.removesuffix("EUR").removesuffix("USD"),
        "quote_asset": quote_asset,
        "market_mapping_status": "EXPLICIT",
        "event_time": event_time.isoformat(),
        "available_time": available.isoformat(),
        "ingestion_time": ingestion.isoformat(),
        "source_snapshot_id": source_id,
        "source": "kraken_rest_public_depth",
        "best_bid": str(bid),
        "best_ask": str(ask),
        "mid_price": str(mid),
        "spread_bps": str(((ask - bid) / mid) * 10_000.0),
        "bid_depth_quote": "1200.0",
        "ask_depth_quote": "1300.0",
        "latency_ms": "42.0",
        "temporal_status": "FORWARD_PUBLIC_REST_INGESTED",
        "runtime_parity_proven": "false",
        "data_quality_status": "FORWARD_PUBLIC_REST_RESEARCH_ONLY",
    }
    row.update(overrides)
    return row


def _write_canonical(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_profile_requires_cross_session_coverage_but_never_becomes_execution_eligible(tmp_path):
    root = tmp_path / "canonical"
    start = datetime(2026, 7, 20, 0, tzinfo=timezone.utc)
    rows = [_row(source_id=f"btc-{index}", event_time=start + timedelta(hours=index * 6)) for index in range(5)]
    _write_canonical(root / "one" / "kraken_spot_microstructure.csv", rows)
    _write_canonical(
        root / "two" / "kraken_spot_microstructure.csv",
        [rows[-1]],
    )
    (root / "raw_spread_depth.csv").write_text("symbol,spread_bps\nBTCEUR,1\n", encoding="utf-8")

    report = build_canonical_microstructure_profile(
        CanonicalMicrostructureProfileConfig(
            run_id="pytest_ready",
            canonical_paths=(root,),
            min_samples_per_symbol=5,
            min_distinct_utc_hours=4,
            min_observation_span=timedelta(hours=24),
        )
    )
    written = write_canonical_microstructure_profile_report(report, tmp_path / "reports")

    assert written.status == "RESEARCH_CALIBRATION_READY"
    assert written.accepted_row_count == 5
    assert written.duplicate_row_count == 1
    assert written.runtime_parity_proven is False
    assert written.execution_eligible is False
    profile = written.profiles[0]
    assert profile.calibration_status == "RESEARCH_CALIBRATION_READY"
    assert profile.distinct_utc_hours == 4
    assert profile.runtime_parity_proven is False
    assert profile.execution_eligible is False
    assert Path(str(written.json_report_path)).exists()
    payload = json.loads(Path(str(written.json_report_path)).read_text(encoding="utf-8"))
    assert payload["execution_eligible"] is False
    assert "automatic cost-model update" in payload["safety_notes"][1]


def test_profile_fails_closed_on_missing_coverage_and_invalid_temporal_or_quote_data(tmp_path):
    root = tmp_path / "canonical"
    start = datetime(2026, 7, 20, 0, tzinfo=timezone.utc)
    valid = _row(source_id="valid", event_time=start)
    invalid_quote = _row(source_id="usd", event_time=start + timedelta(minutes=15), quote_asset="USD")
    invalid_time = _row(
        source_id="bad-time",
        event_time=start + timedelta(minutes=30),
        available_time=(start + timedelta(minutes=29)).isoformat(),
    )
    _write_canonical(
        root / "snapshot" / "kraken_spot_microstructure.csv",
        [valid, invalid_quote, invalid_time],
    )

    report = build_canonical_microstructure_profile(
        CanonicalMicrostructureProfileConfig(
            run_id="pytest_waiting",
            canonical_paths=(root,),
            min_samples_per_symbol=96,
            min_distinct_utc_hours=12,
            min_observation_span=timedelta(hours=24),
        )
    )

    assert report.status == "DATA_QUALITY_REVIEW_REQUIRED"
    assert report.accepted_row_count == 1
    assert report.rejected_row_count == 2
    assert report.rejected_reasons == {
        "event_time_after_available_time": 1,
        "quote_conversion_not_explicitly_supported": 1,
    }
    assert report.profiles[0].reasons == (
        "sample_count_below_minimum",
        "utc_hour_coverage_below_minimum",
        "observation_span_below_minimum",
    )


def test_profile_rejects_conflicting_duplicate_source_ids(tmp_path):
    root = tmp_path / "canonical"
    start = datetime(2026, 7, 20, 0, tzinfo=timezone.utc)
    first = _row(source_id="same-source", event_time=start)
    conflict = _row(source_id="same-source", event_time=start, ask=100.4)
    _write_canonical(root / "a" / "kraken_spot_microstructure.csv", [first])
    _write_canonical(root / "b" / "kraken_spot_microstructure.csv", [conflict])

    report = build_canonical_microstructure_profile(
        CanonicalMicrostructureProfileConfig(
            run_id="pytest_conflict",
            canonical_paths=(root,),
            min_samples_per_symbol=1,
            min_distinct_utc_hours=1,
            min_observation_span=timedelta(seconds=1),
        )
    )

    assert report.accepted_row_count == 1
    assert report.rejected_reasons == {"source_snapshot_id_conflict": 1}
    assert report.status == "DATA_QUALITY_REVIEW_REQUIRED"


def test_cli_profiles_canonical_microstructure_read_only(tmp_path, capsys):
    root = tmp_path / "canonical"
    start = datetime(2026, 7, 20, 0, tzinfo=timezone.utc)
    _write_canonical(
        root / "snapshot" / "kraken_spot_microstructure.csv",
        [_row(source_id="btc-one", event_time=start)],
    )

    exit_code = cli.main(
        [
            "profile-canonical-microstructure",
            "--run-id",
            "pytest_cli_profile",
            "--canonical-paths",
            str(root),
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "WAITING_FOR_MORE_DATA"
    assert output["execution_eligible"] is False
    assert output["profiles"][0]["calibration_status"] == "WAITING_FOR_MORE_DATA"
    assert (tmp_path / "reports" / "pytest_cli_profile.md").exists()


def test_canonical_profile_does_not_import_runtime_or_order_paths():
    root = Path(__file__).resolve().parents[2]
    path = root / "src/autobot/v2/research/canonical_microstructure_profile.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    forbidden = {
        "autobot.v2.order_router",
        "autobot.v2.signal_handler_async",
        "autobot.v2.order_executor_async",
        "autobot.v2.paper_trading",
    }
    assert imports.isdisjoint(forbidden)
