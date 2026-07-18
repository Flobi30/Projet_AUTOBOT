import csv
from hashlib import sha256
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.research.canonical_feature_snapshot import (
    CanonicalFeatureSnapshotConfig,
    build_canonical_feature_snapshot,
)
from autobot.v2.research.verified_feature_vector_publication import (
    load_published_verified_feature_vector,
    publish_verified_feature_vectors,
)


pytestmark = pytest.mark.unit


def _ready_snapshot(tmp_path: Path):
    source_file = tmp_path / "canonical_source.csv"
    fields = (
        "exchange",
        "market_type",
        "symbol",
        "base_asset",
        "quote_asset",
        "market_mapping_status",
        "timeframe",
        "open_timestamp",
        "event_time",
        "available_time",
        "ingestion_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    )
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with source_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(30):
            event = origin + timedelta(minutes=5 * (index + 1))
            close = 100.0 + index
            writer.writerow(
                {
                    "exchange": "kraken",
                    "market_type": "spot",
                    "symbol": "BTCEUR",
                    "base_asset": "BTC",
                    "quote_asset": "EUR",
                    "market_mapping_status": "EXPLICIT",
                    "timeframe": "5m",
                    "open_timestamp": (event - timedelta(minutes=5)).isoformat(),
                    "event_time": event.isoformat(),
                    "available_time": event.isoformat(),
                    "ingestion_time": event.isoformat(),
                    "open": close - 0.5,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "volume": 100.0,
                }
            )
    source_manifest = tmp_path / "canonical_source_manifest.json"
    source_manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "snapshot_id": "canonical_publication_source",
                "fingerprint": "canonical-publication-source-fingerprint",
                "market_type": "spot",
                "files": [{"csv_path": str(source_file)}],
            }
        ),
        encoding="utf-8",
    )
    return build_canonical_feature_snapshot(
        CanonicalFeatureSnapshotConfig(
            run_id="publication_ready_features",
            canonical_manifest_path=source_manifest,
            output_dir=tmp_path / "features",
            manifest_dir=tmp_path / "feature_manifests",
        )
    )


def test_verified_feature_vector_publication_is_atomic_idempotent_and_research_only(tmp_path):
    snapshot = _ready_snapshot(tmp_path)
    observed_at = datetime(2026, 1, 2, tzinfo=timezone.utc)

    first = publish_verified_feature_vectors(
        run_id="daily_20260102",
        feature_snapshot_manifest_path=Path(str(snapshot.manifest_path)),
        observed_at=observed_at,
        output_dir=tmp_path / "publications",
    )
    second = publish_verified_feature_vectors(
        run_id="daily_20260102",
        feature_snapshot_manifest_path=Path(str(snapshot.manifest_path)),
        observed_at=observed_at,
        output_dir=tmp_path / "publications",
    )

    payload = json.loads(Path(first.output_path).read_text(encoding="utf-8"))
    assert first.publication_id == second.publication_id
    assert first.output_path == second.output_path
    assert first.vector_count == 1
    assert payload["research_only"] is True
    assert payload["paper_capital_allowed"] is False
    assert payload["live_allowed"] is False
    assert payload["promotable"] is False
    assert payload["vectors"][0]["market_identity"]["symbol"] == "BTCEUR"
    assert load_published_verified_feature_vector(first.output_path, symbol="BTCEUR", timeframe="5m").fingerprint


def test_verified_feature_vector_publication_rejects_tampered_existing_evidence(tmp_path):
    snapshot = _ready_snapshot(tmp_path)
    observed_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    publication = publish_verified_feature_vectors(
        run_id="daily_20260102_tamper",
        feature_snapshot_manifest_path=Path(str(snapshot.manifest_path)),
        observed_at=observed_at,
        output_dir=tmp_path / "publications",
    )
    path = Path(publication.output_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["vectors"][0]["values"][0]["value"] = 999.0
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint mismatch"):
        publish_verified_feature_vectors(
            run_id="daily_20260102_tamper",
            feature_snapshot_manifest_path=Path(str(snapshot.manifest_path)),
            observed_at=observed_at,
            output_dir=tmp_path / "publications",
        )


def test_published_vector_is_rechecked_against_the_canonical_bundle(tmp_path):
    snapshot = _ready_snapshot(tmp_path)
    publication = publish_verified_feature_vectors(
        run_id="daily_20260102_source_check",
        feature_snapshot_manifest_path=Path(str(snapshot.manifest_path)),
        observed_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        output_dir=tmp_path / "publications",
    )
    path = Path(publication.output_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["vectors"][0]["values"][0]["value"] = 999.0
    evidence = {key: value for key, value in payload.items() if key not in {"publication_id", "publication_fingerprint"}}
    fingerprint = sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    payload["publication_fingerprint"] = fingerprint
    payload["publication_id"] = f"verified_vectors_{fingerprint[:20]}"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match canonical bundle"):
        load_published_verified_feature_vector(path, symbol="BTCEUR", timeframe="5m")


def test_verified_feature_vector_publication_does_not_import_runtime_or_execution_paths():
    source = Path("src/autobot/v2/research/verified_feature_vector_publication.py").read_text(encoding="utf-8")
    forbidden = ("autobot.v2.order_router", "autobot.v2.signal_handler_async", "autobot.v2.paper_trading")

    assert all(item not in source for item in forbidden)
