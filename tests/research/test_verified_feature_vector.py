from __future__ import annotations

from datetime import datetime, timezone

import pytest

from autobot.v2.contracts import FeatureSnapshotReference
from autobot.v2.research.verified_feature_vector import (
    VerifiedFeatureVectorError,
    parse_verified_feature_vectors,
    verified_feature_vector_to_mapping,
)


pytestmark = pytest.mark.unit


def _snapshot() -> FeatureSnapshotReference:
    return FeatureSnapshotReference(
        feature_snapshot_id="features_vector_fixture",
        fingerprint="logical-feature-fingerprint",
        snapshot_kind="CANONICAL_FEATURE_SNAPSHOT",
        source_snapshot_id="ohlcv_vector_fixture",
        source_snapshot_fingerprint="source-fingerprint",
        feature_registry_fingerprint="registry-fingerprint",
        feature_versions={"momentum": "1", "volatility": "1"},
        runtime_parity_proven=True,
        material_verified=True,
        bundle_content_fingerprint="bundle-content-vector-fixture",
    )


def _payload() -> dict:
    observed_at = "2026-07-12T10:01:00+00:00"
    return {
        "features_vector_fixture": {
            "feature_snapshot_id": "features_vector_fixture",
            "bundle_content_fingerprint": "bundle-content-vector-fixture",
            "feature_registry_fingerprint": "registry-fingerprint",
            "source_snapshot_id": "ohlcv_vector_fixture",
            "observed_at": observed_at,
            "market_identity": {
                "exchange": "kraken",
                "market_type": "spot",
                "symbol": "BTCEUR",
                "base_asset": "BTC",
                "quote_asset": "EUR",
            },
            "timeframe": "5m",
            "values": [
                {
                    "feature_id": "momentum",
                    "feature_version": "1",
                    "event_time": "2026-07-12T10:00:00+00:00",
                    "available_time": observed_at,
                    "source_snapshot_id": "ohlcv_vector_fixture",
                    "value": 20.0,
                    "status": "ready",
                },
                {
                    "feature_id": "volatility",
                    "feature_version": "1",
                    "event_time": "2026-07-12T10:00:00+00:00",
                    "available_time": observed_at,
                    "source_snapshot_id": "ohlcv_vector_fixture",
                    "value": 8.0,
                    "status": "ready",
                },
            ],
        }
    }


def test_verified_feature_vector_requires_exact_snapshot_and_available_values():
    observed_at = datetime(2026, 7, 12, 10, 1, tzinfo=timezone.utc)
    vector = parse_verified_feature_vectors(
        _payload(),
        snapshots=(_snapshot(),),
        observed_at=observed_at,
    )[0]

    assert vector.feature_snapshot.feature_snapshot_id == "features_vector_fixture"
    assert vector.fingerprint

    round_trip = parse_verified_feature_vectors(
        {vector.feature_snapshot.feature_snapshot_id: verified_feature_vector_to_mapping(vector)},
        snapshots=(_snapshot(),),
        observed_at=observed_at,
    )[0]
    assert round_trip.fingerprint == vector.fingerprint


def test_verified_feature_vector_rejects_tampered_bundle_or_feature_set():
    observed_at = datetime(2026, 7, 12, 10, 1, tzinfo=timezone.utc)
    tampered = _payload()
    tampered["features_vector_fixture"]["bundle_content_fingerprint"] = "tampered"

    with pytest.raises(VerifiedFeatureVectorError, match="bundle_content_fingerprint_mismatch"):
        parse_verified_feature_vectors(tampered, snapshots=(_snapshot(),), observed_at=observed_at)

    missing = _payload()
    missing["features_vector_fixture"]["values"] = missing["features_vector_fixture"]["values"][:1]
    with pytest.raises(VerifiedFeatureVectorError, match="versions must exactly match"):
        parse_verified_feature_vectors(missing, snapshots=(_snapshot(),), observed_at=observed_at)
