from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research.derivatives_feature_snapshot import (
    DerivativesFeatureSnapshotConfig,
    build_derivatives_feature_snapshot,
)
from autobot.v2.research.manifested_experiment import build_manifested_experiment_spec


pytestmark = pytest.mark.unit


AS_OF = datetime(2026, 7, 12, tzinfo=timezone.utc)


def test_derivatives_snapshot_is_point_in_time_and_keeps_perpetual_usd_identity(tmp_path):
    manifest = _derivatives_manifest(tmp_path, basis_ready=True, oi_ready=True, include_future_row=True)

    snapshot = build_derivatives_feature_snapshot(
        DerivativesFeatureSnapshotConfig(
            run_id="derivatives_ready",
            derivatives_manifest_path=manifest,
            as_of_time=AS_OF,
            output_dir=tmp_path / "output",
            manifest_dir=tmp_path / "manifests",
        )
    )

    assert snapshot.snapshot_kind == "DERIVATIVES_POINT_IN_TIME"
    assert snapshot.status == "READY"
    assert snapshot.runtime_parity_proven is False
    assert "DERIVATIVES_RUNTIME_PARITY_NOT_PROVEN" in snapshot.blockers
    assert snapshot.temporal_contract["future_rows_excluded"] == 1
    assert snapshot.basis_contract["implicit_usd_eur_conversion_allowed"] is False
    assert snapshot.datasets["funding"]["row_count"] == 3
    rows = _feature_rows(snapshot)
    assert {row["market_type"] for row in rows} == {"perpetual"}
    assert {row["quote_asset"] for row in rows} == {"USD"}
    assert {row["symbol"] for row in rows} == {"PF_XBTUSD"}


def test_derivatives_snapshot_waits_for_basis_and_open_interest_history(tmp_path):
    manifest = _derivatives_manifest(tmp_path, basis_ready=False, oi_ready=False)

    snapshot = build_derivatives_feature_snapshot(
        DerivativesFeatureSnapshotConfig(
            run_id="derivatives_waiting",
            derivatives_manifest_path=manifest,
            as_of_time=AS_OF,
            output_dir=tmp_path / "output",
            manifest_dir=tmp_path / "manifests",
        )
    )

    assert snapshot.status == "WAITING_FOR_MORE_DATA"
    assert "BASIS_HISTORY_WAITING" in snapshot.blockers
    assert "OPEN_INTEREST_HISTORY_WAITING" in snapshot.blockers
    assert snapshot.paper_capital_allowed is False
    assert snapshot.live_allowed is False
    assert snapshot.promotable is False


def test_derivatives_snapshot_rejects_unverified_basis_rows(tmp_path):
    manifest = _derivatives_manifest(tmp_path, basis_ready=True, oi_ready=True, basis_confidence="BASIS_REFERENCE_UNVERIFIED")

    snapshot = build_derivatives_feature_snapshot(
        DerivativesFeatureSnapshotConfig(
            run_id="derivatives_bad_basis",
            derivatives_manifest_path=manifest,
            as_of_time=AS_OF,
            output_dir=tmp_path / "output",
            manifest_dir=tmp_path / "manifests",
        )
    )

    assert snapshot.status == "DATA_MISSING"
    assert "BASIS_UNVERIFIED_ROWS_EXCLUDED" in snapshot.blockers
    assert "FEATURE_DATA_MISSING" in snapshot.blockers


def test_manifested_experiment_binds_derivatives_materially_without_local_paths(tmp_path):
    derivatives_manifest = _derivatives_manifest(tmp_path / "derivatives", basis_ready=True, oi_ready=True)
    derivatives_snapshot = build_derivatives_feature_snapshot(
        DerivativesFeatureSnapshotConfig(
            run_id="derivatives_for_experiment",
            derivatives_manifest_path=derivatives_manifest,
            as_of_time=AS_OF,
            output_dir=tmp_path / "derivatives_output",
            manifest_dir=tmp_path / "derivatives_manifests",
        )
    )
    spot_manifest = tmp_path / "spot_features.json"
    spot_manifest.write_text(
        json.dumps(
            {
                "status": "READY",
                "parity_ok": True,
                "feature_count": 1,
                "feature_snapshot_id": "spot_features_v1",
                "fingerprint": "spot-feature-fingerprint",
                "source_snapshot_id": "spot_ohlcv_v2",
                "source_snapshot_fingerprint": "spot-source-fingerprint",
                "feature_registry_fingerprint": "registry-fingerprint",
                "feature_versions": {"momentum_3_bps": "1.0.0"},
                "ingestion_time_unknown_count": 0,
                "runtime_parity_proven": True,
            }
        ),
        encoding="utf-8",
    )

    spec, _spot = build_manifested_experiment_spec(
        hypothesis_id="funding_basis",
        template_id="funding_basis_v1",
        thesis="test only",
        code_commit="abc123",
        feature_snapshot_manifest=spot_manifest,
        derivatives_snapshot_manifest=derivatives_snapshot.manifest_path,
        parameters={"horizon_hours": 4},
        seed=7,
        cost_model={"profile": "research_stress"},
    )

    assert spec.data_snapshot_id.startswith("combined_")
    assert spec.environment["derivatives_snapshot"]["snapshot_kind"] == "DERIVATIVES_POINT_IN_TIME"
    assert "manifest_path" not in spec.environment["feature_snapshot"]
    assert "manifest_path" not in spec.environment["derivatives_snapshot"]
    assert spec.environment["runtime_parity_proven"] is False
    assert set(spec.feature_versions) == {
        "momentum_3_bps",
        "funding_rate_relative",
        "basis_bps",
        "open_interest_change_24_pct",
    }


def test_derivatives_feature_snapshot_cli_is_registered():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "materialize-derivatives-feature-snapshot",
            "--derivatives-manifest",
            "data/research/manifests/derivatives.json",
            "--as-of-time",
            "2026-07-12T00:00:00Z",
        ]
    )

    assert args.command == "materialize-derivatives-feature-snapshot"
    assert args.as_of_time == "2026-07-12T00:00:00Z"

    runner_args = parser.parse_args(
        [
            "alpha-hypothesis-runner",
            "--hypothesis-id",
            "funding_basis",
            "--feature-snapshot-manifest",
            "spot.json",
            "--derivatives-feature-snapshot-manifest",
            "derivatives.json",
        ]
    )
    assert runner_args.derivatives_feature_snapshot_manifest == "derivatives.json"


def _derivatives_manifest(
    tmp_path: Path,
    *,
    basis_ready: bool,
    oi_ready: bool,
    basis_confidence: str = "MARK_INDEX_SAME_QUOTE",
    include_future_row: bool = False,
) -> Path:
    funding_path = tmp_path / "funding.csv"
    basis_path = tmp_path / "basis.csv"
    ticker_path = tmp_path / "tickers.csv"
    start = datetime(2026, 7, 10, tzinfo=timezone.utc)
    funding_rows = []
    basis_rows = []
    for index in range(3):
        event_time = start + timedelta(hours=index)
        funding_rows.append(
            _row(
                event_time,
                available_time=(AS_OF - timedelta(days=1)).isoformat(),
                temporal_status="HISTORICAL_BACKFILL_AVAILABLE_AT_INGESTION",
                funding_rate_relative="0.0001",
            )
        )
        basis_rows.append(
            _row(
                event_time,
                confidence_status=basis_confidence,
                basis_bps="12.5",
                calculation_method="mark_over_index_same_quote",
            )
        )
    if include_future_row:
        funding_rows.append(
            _row(
                AS_OF + timedelta(hours=1),
                funding_rate_relative="0.0002",
                temporal_status="AVAILABLE_AT_EVENT",
            )
        )
    ticker_rows = [
        _row(start + timedelta(minutes=index * 15), open_interest=str(100 + index))
        for index in range(25)
    ]
    for row in funding_rows:
        row.pop("quote_asset", None)
    _write_rows(funding_path, funding_rows)
    _write_rows(basis_path, basis_rows)
    _write_rows(ticker_path, ticker_rows)
    payload = {
        "schema_version": 2,
        "snapshot_id": "kraken_futures_test",
        "fingerprint": "collector-fingerprint",
        "funding_history_ready": True,
        "basis_history_ready": basis_ready,
        "open_interest_history_ready": oi_ready,
        "funding_history_path": str(funding_path),
        "basis_history_path": str(basis_path),
        "open_interest_history_path": str(ticker_path),
        "mappings": [
            {
                "futures_symbol": "PF_XBTUSD",
                "base_asset": "BTC",
                "quote_asset": "USD",
                "autobot_spot_symbol": "BTCZEUR",
            }
        ],
    }
    path = tmp_path / "derivatives_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _row(event_time: datetime, **overrides: str) -> dict[str, str]:
    timestamp = event_time.isoformat()
    return {
        "exchange": "kraken_futures",
        "futures_symbol": "PF_XBTUSD",
        "base_asset": "BTC",
        "quote_asset": "USD",
        "timestamp": timestamp,
        "event_time": timestamp,
        "available_time": overrides.pop("available_time", timestamp),
        "ingestion_time": AS_OF.isoformat(),
        "temporal_status": overrides.pop("temporal_status", "AVAILABLE_AT_EVENT"),
        **overrides,
    }


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _feature_rows(snapshot) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in snapshot.files:
        with Path(item.csv_path).open("r", encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    return rows
