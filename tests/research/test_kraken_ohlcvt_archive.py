from __future__ import annotations

import csv
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from autobot.v2.research.canonical_ohlcv_store import CanonicalOHLCVConfig, build_canonical_ohlcv_snapshot
from autobot.v2.research.canonical_feature_snapshot import CanonicalFeatureSnapshotConfig, build_canonical_feature_snapshot
from autobot.v2.research.data_capability_scanner import build_data_capability_scan_report
from autobot.v2.research.kraken_ohlcvt_archive import (
    HISTORICAL_ARCHIVE_STATUS,
    KrakenOhlcvtArchiveError,
    KrakenOhlcvtArchiveImportConfig,
    import_kraken_ohlcvt_archive,
)
from autobot.v2.research.kraken_symbol_mapping import KrakenPublicPairMapping


pytestmark = pytest.mark.unit


def _mapping() -> KrakenPublicPairMapping:
    return KrakenPublicPairMapping(
        autobot_symbol="BTCEUR",
        kraken_ohlcv_symbol="XXBTZEUR",
        runtime_symbol="XXBTZEUR",
        aliases=("BTCEUR", "XBTZEUR", "XXBTZEUR", "XBT/EUR"),
        altname="XBTEUR",
        wsname="XBT/EUR",
        base_asset="BTC",
        quote_asset="EUR",
        market_mapping_status="EXPLICIT",
    )


def _archive(path: Path, *, duplicate: bool = False) -> Path:
    content = (
        "timestamp,open,high,low,close,volume,trades\n"
        "2025-01-01T00:00:00+00:00,100,102,99,101,3,12\n"
        "2025-01-01T00:05:00+00:00,101,103,100,102,4,15\n"
    )
    if duplicate:
        content += "2025-01-01T00:05:00+00:00,101,103,100,102,4,15\n"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Kraken_OHLCVT/XXBTZEUR_5.csv", content)
    return path


def test_import_official_archive_keeps_raw_provenance_and_blocks_runtime_parity(tmp_path: Path) -> None:
    archive = _archive(tmp_path / "official.zip", duplicate=True)
    result = import_kraken_ohlcvt_archive(
        KrakenOhlcvtArchiveImportConfig(
            run_id="pytest_archive",
            archive_path=archive,
            symbols=("BTCEUR",),
            timeframes=("5m",),
            raw_dir=tmp_path / "raw",
            normalized_dir=tmp_path / "normalized",
            manifest_dir=tmp_path / "manifests",
            report_dir=tmp_path / "reports",
        ),
        imported_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        symbol_mappings={"BTCEUR": _mapping()},
    )

    assert result.status == "COMPLETE"
    assert result.blockers == ("HISTORICAL_ARCHIVE_NOT_RUNTIME_PARITY",)
    assert result.runtime_parity_proven is False
    assert result.paper_capital_allowed is False
    assert result.live_allowed is False
    member = result.members[0]
    assert member.row_count == 2
    assert member.duplicate_count == 1
    assert Path(member.raw_path).read_bytes().startswith(b"timestamp,open")
    with Path(member.normalized_path).open("r", encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["temporal_status"] == HISTORICAL_ARCHIVE_STATUS
    assert row["available_time"] == "2025-01-01T00:05:00+00:00"
    assert row["ingestion_time"] == "2026-07-20T00:00:00+00:00"
    assert json.loads(row["metadata"])["historical_archive"] is True
    manifest = json.loads(Path(str(result.manifest_path)).read_text(encoding="utf-8"))
    assert manifest["temporal_contract"]["runtime_parity_proven"] is False
    assert manifest["paper_capital_allowed"] is False


def test_archive_temporal_status_survives_canonicalization(tmp_path: Path) -> None:
    archive = _archive(tmp_path / "official.zip")
    result = import_kraken_ohlcvt_archive(
        KrakenOhlcvtArchiveImportConfig(
            run_id="pytest_canonical_archive",
            archive_path=archive,
            symbols=("BTCEUR",),
            timeframes=("5m",),
            raw_dir=tmp_path / "raw",
            normalized_dir=tmp_path / "normalized",
            manifest_dir=tmp_path / "manifests",
            report_dir=tmp_path / "reports",
        ),
        imported_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        symbol_mappings={"BTCEUR": _mapping()},
    )
    snapshot = build_canonical_ohlcv_snapshot(
        CanonicalOHLCVConfig(
            run_id="pytest_canonical",
            raw_paths=(Path(result.members[0].normalized_path),),
            output_dir=tmp_path / "canonical",
            manifest_dir=tmp_path / "canonical_manifests",
            market_mappings={"BTCEUR": {"base_asset": "BTC", "quote_asset": "EUR"}},
        )
    )
    with Path(snapshot.files[0].csv_path).open("r", encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["temporal_status"] == HISTORICAL_ARCHIVE_STATUS
    assert row["availability_basis"] == "OFFICIAL_ARCHIVE_COMPLETED_BAR_ASSUMPTION"
    assert row["ingestion_time"] == "2026-07-20T00:00:00+00:00"
    features = build_canonical_feature_snapshot(
        CanonicalFeatureSnapshotConfig(
            run_id="pytest_archive_features",
            canonical_manifest_path=Path(str(snapshot.manifest_path)),
            output_dir=tmp_path / "features",
            manifest_dir=tmp_path / "feature_manifests",
        )
    )
    assert features.historical_runtime_parity_unproven_count == 2
    assert features.runtime_parity_proven is False
    assert "HISTORICAL_DATA_RUNTIME_PARITY_NOT_PROVEN" in features.blockers


def test_archive_import_rejects_missing_member_and_size_budget(tmp_path: Path) -> None:
    archive = _archive(tmp_path / "official.zip")
    with pytest.raises(KrakenOhlcvtArchiveError, match="lacks requested"):
        import_kraken_ohlcvt_archive(
            KrakenOhlcvtArchiveImportConfig(
                run_id="pytest_missing",
                archive_path=archive,
                symbols=("BTCEUR",),
                timeframes=("1h",),
                raw_dir=tmp_path / "raw",
                normalized_dir=tmp_path / "normalized",
                manifest_dir=tmp_path / "manifests",
                report_dir=tmp_path / "reports",
            ),
            symbol_mappings={"BTCEUR": _mapping()},
        )


def test_archive_import_applies_per_member_row_budget(tmp_path: Path) -> None:
    archive = _archive(tmp_path / "official.zip")
    with pytest.raises(KrakenOhlcvtArchiveError, match="max_rows_per_member"):
        import_kraken_ohlcvt_archive(
            KrakenOhlcvtArchiveImportConfig(
                run_id="pytest_rows",
                archive_path=archive,
                symbols=("BTCEUR",),
                timeframes=("5m",),
                raw_dir=tmp_path / "raw",
                normalized_dir=tmp_path / "normalized",
                manifest_dir=tmp_path / "manifests",
                report_dir=tmp_path / "reports",
                max_rows_per_member=1,
            ),
            symbol_mappings={"BTCEUR": _mapping()},
        )


def test_archive_import_rejects_future_closed_bar(tmp_path: Path) -> None:
    archive = _archive(tmp_path / "official.zip")
    with pytest.raises(KrakenOhlcvtArchiveError, match="not closed at import time"):
        import_kraken_ohlcvt_archive(
            KrakenOhlcvtArchiveImportConfig(
                run_id="pytest_future",
                archive_path=archive,
                symbols=("BTCEUR",),
                timeframes=("5m",),
                raw_dir=tmp_path / "raw",
                normalized_dir=tmp_path / "normalized",
                manifest_dir=tmp_path / "manifests",
                report_dir=tmp_path / "reports",
            ),
            imported_at=datetime(2025, 1, 1, 0, 4, tzinfo=timezone.utc),
            symbol_mappings={"BTCEUR": _mapping()},
        )


def test_archive_rows_do_not_become_runtime_ohlcv_capability(tmp_path: Path) -> None:
    archive = _archive(tmp_path / "official.zip")
    result = import_kraken_ohlcvt_archive(
        KrakenOhlcvtArchiveImportConfig(
            run_id="pytest_scanner_archive",
            archive_path=archive,
            symbols=("BTCEUR",),
            timeframes=("5m",),
            raw_dir=tmp_path / "raw",
            normalized_dir=tmp_path / "normalized",
            manifest_dir=tmp_path / "manifests",
            report_dir=tmp_path / "reports",
        ),
        symbol_mappings={"BTCEUR": _mapping()},
    )
    report = build_data_capability_scan_report(
        run_id="pytest_scanner",
        data_roots=(Path(result.members[0].normalized_path).parent,),
        memory_path=tmp_path / "memory.sqlite3",
    )
    spot_ohlcv = next(item for item in report.capabilities if item.capability_id == "spot_ohlcv")
    assert spot_ohlcv.available is False
    assert spot_ohlcv.blockers == ("spot_ohlcv_missing",)
    with pytest.raises(KrakenOhlcvtArchiveError, match="max_selected_uncompressed_bytes"):
        import_kraken_ohlcvt_archive(
            KrakenOhlcvtArchiveImportConfig(
                run_id="pytest_budget",
                archive_path=archive,
                symbols=("BTCEUR",),
                timeframes=("5m",),
                raw_dir=tmp_path / "raw",
                normalized_dir=tmp_path / "normalized",
                manifest_dir=tmp_path / "manifests",
                report_dir=tmp_path / "reports",
                max_selected_uncompressed_bytes=1,
            ),
            symbol_mappings={"BTCEUR": _mapping()},
        )
