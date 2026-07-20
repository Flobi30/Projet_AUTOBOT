from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from autobot.v2.research.canonical_microstructure_store import (
    CanonicalMicrostructureConfig,
    adapt_spread_depth_row,
    build_canonical_microstructure_snapshot,
)
from autobot.v2.research.data_capability_scanner import build_data_capability_scan_report


pytestmark = pytest.mark.unit


def _row(**overrides: str) -> dict[str, str]:
    base = {
        "timestamp_local": "2026-07-20T10:00:01+00:00",
        "timestamp_exchange": "2026-07-20T10:00:00+00:00",
        "event_time": "2026-07-20T10:00:00+00:00",
        "available_time": "2026-07-20T10:00:01+00:00",
        "ingestion_time": "2026-07-20T10:00:01+00:00",
        "symbol": "BTCZEUR",
        "base_asset": "BTC",
        "quote_asset": "EUR",
        "market_mapping_status": "EXPLICIT",
        "source_snapshot_id": "kraken_depth_fixture_001",
        "temporal_status": "FORWARD_PUBLIC_REST_INGESTED",
        "runtime_parity_proven": "false",
        "exchange_clock_ahead_seconds": "0.0",
        "source": "kraken_rest_public_depth",
        "best_bid": "100.0",
        "best_ask": "100.2",
        "mid_price": "100.1",
        "spread_bps": str((0.2 / 100.1) * 10_000.0),
        "bid_depth_eur": "1200.0",
        "ask_depth_eur": "1300.0",
        "latency_ms": "42.0",
    }
    base.update(overrides)
    return base


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_canonical_microstructure_preserves_point_in_time_provenance_and_is_research_only(tmp_path):
    raw = tmp_path / "raw.csv"
    _write_rows(raw, [_row(), _row()])

    snapshot = build_canonical_microstructure_snapshot(
        CanonicalMicrostructureConfig(
            run_id="pytest_microstructure",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical",
            manifest_dir=tmp_path / "manifests",
            report_dir=tmp_path / "reports",
        )
    )

    assert snapshot.raw_row_count == 2
    assert snapshot.canonical_row_count == 1
    assert snapshot.duplicate_count == 1
    assert snapshot.runtime_parity_proven is False
    assert snapshot.execution_eligible is False
    assert snapshot.symbols == ("BTCZEUR",)
    assert Path(str(snapshot.manifest_path)).exists()
    rows = list(csv.DictReader(Path(str(snapshot.canonical_csv_path)).open(encoding="utf-8")))
    assert rows[0]["event_time"] == "2026-07-20T10:00:00+00:00"
    assert rows[0]["available_time"] == "2026-07-20T10:00:01+00:00"
    assert rows[0]["ingestion_time"] == "2026-07-20T10:00:01+00:00"
    assert rows[0]["quote_asset"] == "EUR"
    assert rows[0]["runtime_parity_proven"] == "False"
    manifest = json.loads(Path(str(snapshot.manifest_path)).read_text(encoding="utf-8"))
    assert manifest["fingerprint"] == snapshot.fingerprint
    assert manifest["execution_eligible"] is False

    report = build_data_capability_scan_report(
        run_id="pytest_microstructure_scan",
        data_roots=(tmp_path,),
        memory_path=tmp_path / "memory.json",
    )
    capabilities = {item.capability_id: item for item in report.capabilities}
    assert capabilities["spread_history"].quality_status == "forward_captured_research_only"
    assert capabilities["orderbook_depth_snapshots"].row_count == 1
    assert "canonical_forward_rest_capture_no_runtime_parity" in capabilities["spread_history"].notes


def test_canonical_microstructure_quarantines_implicit_quote_conversion_and_inconsistent_spread(tmp_path):
    raw = tmp_path / "raw.csv"
    _write_rows(
        raw,
        [
            _row(source_snapshot_id="bad_quote", quote_asset="USD"),
            _row(source_snapshot_id="bad_spread", spread_bps="999"),
        ],
    )

    snapshot = build_canonical_microstructure_snapshot(
        CanonicalMicrostructureConfig(
            run_id="pytest_microstructure_quarantine",
            raw_paths=(raw,),
            output_dir=tmp_path / "canonical",
            manifest_dir=tmp_path / "manifests",
            report_dir=tmp_path / "reports",
        )
    )

    assert snapshot.canonical_row_count == 0
    assert snapshot.quarantine_count == 2
    quarantined = json.loads(Path(str(snapshot.quarantine_path)).read_text(encoding="utf-8"))
    assert {item["reason"] for item in quarantined} == {
        "quote_conversion_not_explicitly_supported",
        "spread_bps_inconsistent_with_best_quotes",
    }


def test_canonical_microstructure_rejects_runtime_parity_claim_and_naive_times():
    with pytest.raises(ValueError, match="rest_capture_cannot_claim_runtime_parity"):
        adapt_spread_depth_row(
            _row(runtime_parity_proven="true"),
            exchange="kraken",
            market_type="spot",
            raw_source_path="raw.csv",
            raw_source_sha256="a" * 64,
            raw_source_row_number=2,
        )
    with pytest.raises(ValueError, match="event_time_naive"):
        adapt_spread_depth_row(
            _row(event_time="2026-07-20T10:00:00"),
            exchange="kraken",
            market_type="spot",
            raw_source_path="raw.csv",
            raw_source_sha256="a" * 64,
            raw_source_row_number=2,
        )


def test_canonical_microstructure_rejects_event_after_ingestion():
    row = _row(
        event_time="2026-07-20T10:00:02+00:00",
        available_time="2026-07-20T10:00:02+00:00",
        ingestion_time="2026-07-20T10:00:01+00:00",
    )
    with pytest.raises(ValueError, match="ingestion_time cannot precede available_time"):
        adapt_spread_depth_row(
            row,
            exchange="kraken",
            market_type="spot",
            raw_source_path="raw.csv",
            raw_source_sha256="a" * 64,
            raw_source_row_number=2,
        )
