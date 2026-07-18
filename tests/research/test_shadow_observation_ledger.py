from __future__ import annotations

import ast
import csv
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from pathlib import Path

import pytest

from autobot.v2.contracts import (
    AlphaSignal,
    FeatureSnapshotReference,
    FeatureValue,
    MarketIdentity,
    RiskMandateReference,
    TargetPortfolio,
    VerifiedFeatureVector,
)
from autobot.v2.research.shadow_governance import ShadowObservation, StrategyArtifact
from autobot.v2.research.shadow_observation_ledger import (
    ShadowObservationLedger,
    ShadowObservationLedgerError,
    build_shadow_observation_from_target,
    verified_feature_vectors_fingerprint,
)
from autobot.v2.research.portfolio_construction import build_target_portfolio
from autobot.v2.research.canonical_feature_snapshot import (
    CanonicalFeatureSnapshotConfig,
    build_canonical_feature_snapshot,
    load_verified_feature_vector_from_canonical_snapshot,
)
from autobot.v2.research.runtime_shadow_preview import preview_runtime_buy_signal
from autobot.v2.research.verified_feature_vector import verified_feature_vector_to_mapping
from autobot.v2.research.verified_feature_vector_publication import (
    load_published_verified_feature_vector,
    publish_verified_feature_vectors,
)


pytestmark = pytest.mark.integration


def _vector() -> VerifiedFeatureVector:
    market = MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR")
    snapshot = FeatureSnapshotReference(
        feature_snapshot_id="features_shadow_observation",
        fingerprint="features-logical-fingerprint",
        snapshot_kind="CANONICAL_FEATURE_SNAPSHOT",
        source_snapshot_id="ohlcv_shadow_observation",
        source_snapshot_fingerprint="ohlcv-source-fingerprint",
        feature_registry_fingerprint="feature-registry-fingerprint",
        feature_versions={"momentum": "1.0.0", "volatility": "1.0.0"},
        runtime_parity_proven=True,
        material_verified=True,
        bundle_content_fingerprint="bundle-content-fingerprint",
    )
    timestamp = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
    return VerifiedFeatureVector(
        feature_snapshot=snapshot,
        market=market,
        timeframe="5m",
        observed_at=timestamp,
        values=(
            FeatureValue("momentum", "1.0.0", market, "5m", timestamp, timestamp, "ohlcv_shadow_observation", 12.0),
            FeatureValue("volatility", "1.0.0", market, "5m", timestamp, timestamp, "ohlcv_shadow_observation", 4.0),
        ),
    )


def _canonical_vector(tmp_path, *, include_manifest: bool = False) -> VerifiedFeatureVector | tuple[VerifiedFeatureVector, Path]:
    """Create one actual READY canonical bundle for the cross-boundary test."""

    source_file = tmp_path / "canonical_shadow_source.csv"
    fields = (
        "exchange", "market_type", "symbol", "base_asset", "quote_asset", "market_mapping_status",
        "timeframe", "open_timestamp", "event_time", "available_time", "ingestion_time",
        "open", "high", "low", "close", "volume",
    )
    origin = datetime(2026, 7, 18, 10, tzinfo=timezone.utc)
    with source_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(30):
            event = origin + timedelta(minutes=5 * (index + 1))
            price = 100.0 + index
            writer.writerow(
                {
                    "exchange": "kraken", "market_type": "spot", "symbol": "BTCEUR",
                    "base_asset": "BTC", "quote_asset": "EUR", "market_mapping_status": "EXPLICIT",
                    "timeframe": "5m", "open_timestamp": (event - timedelta(minutes=5)).isoformat(),
                    "event_time": event.isoformat(), "available_time": event.isoformat(),
                    "ingestion_time": event.isoformat(), "open": price - 0.5, "high": price + 1.0,
                    "low": price - 1.0, "close": price, "volume": 100.0,
                }
            )
    source_manifest = tmp_path / "canonical_shadow_source_manifest.json"
    source_manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "snapshot_id": "canonical_shadow_source",
                "fingerprint": "canonical-shadow-source-fingerprint",
                "market_type": "spot",
                "files": [{"csv_path": str(source_file)}],
            }
        ),
        encoding="utf-8",
    )
    snapshot = build_canonical_feature_snapshot(
        CanonicalFeatureSnapshotConfig(
            run_id="canonical_shadow_vector",
            canonical_manifest_path=source_manifest,
            output_dir=tmp_path / "features",
            manifest_dir=tmp_path / "feature_manifests",
        )
    )
    assert snapshot.status == "READY"
    with Path(snapshot.files[0].csv_path).open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row["status"] == "READY":
            grouped.setdefault(row["event_time"], []).append(row)
    event_time, event_rows = next(
        (event, values)
        for event, values in sorted(grouped.items())
        if {row["feature_id"] for row in values} == set(snapshot.feature_ids)
    )
    vector = load_verified_feature_vector_from_canonical_snapshot(
        Path(str(snapshot.manifest_path)),
        symbol="BTCEUR",
        timeframe="5m",
        event_time=datetime.fromisoformat(event_time),
        observed_at=max(datetime.fromisoformat(row["available_time"]) for row in event_rows),
    )
    return (vector, Path(str(snapshot.manifest_path))) if include_manifest else vector


def _artifact(vector: VerifiedFeatureVector, *, status: str = "SHADOW_ELIGIBLE") -> StrategyArtifact:
    return StrategyArtifact(
        strategy_id="trend_momentum",
        strategy_version="shadow-observation-v1",
        code_commit="shadow-observation-fixture",
        data_snapshot_id=vector.feature_snapshot.source_snapshot_id,
        feature_versions=dict(vector.feature_snapshot.feature_versions),
        parameters={"fixture": True},
        risk_mandate_fingerprint="shadow-observation-mandate",
        validation_manifest_fingerprint="shadow-observation-validation",
        feature_snapshots=(vector.feature_snapshot,),
        risk_mandate=RiskMandateReference(
            mandate_id="shadow-observation-mandate",
            strategy_id="trend_momentum",
            fingerprint="shadow-observation-mandate",
            mode_allowed="shadow",
            capital_max_eur=0.0,
            shadow_notional_max_eur=1.0,
            expires_at="2027-01-01T00:00:00+00:00",
            human_approved_required_for_risk_increase=True,
        ),
        status=status,
        experiment_id="shadow-observation-experiment",
        experiment_fingerprint="shadow-observation-experiment-fingerprint",
        human_approval_reference="shadow-observation-human-review",
    )


def _observation(artifact: StrategyArtifact, vector: VerifiedFeatureVector, *, fingerprint: str | None = None) -> ShadowObservation:
    timestamp = vector.observed_at
    return ShadowObservation(
        artifact_id=artifact.artifact_id,
        observed_at=timestamp,
        data_available_at=timestamp,
        source_snapshot_id=artifact.data_snapshot_id,
        feature_fingerprint=fingerprint or verified_feature_vectors_fingerprint((vector,)),
        target_portfolio=TargetPortfolio(
            decision_id="shadow-observation-decision",
            generated_at=timestamp,
            target_weights={"BTCEUR": 0.1},
            reserve_cash_weight=0.9,
            rationale={"BTCEUR": "research_only"},
        ),
    )


def test_shadow_observation_ledger_records_exact_vectors_append_only_and_idempotently(tmp_path):
    vector = _vector()
    artifact = _artifact(vector)
    observation = _observation(artifact, vector)
    ledger = ShadowObservationLedger(tmp_path / "shadow_observations.sqlite3")

    first = ledger.record(artifact=artifact, observation=observation, feature_vectors=(vector,))
    duplicate = ledger.record(artifact=artifact, observation=observation, feature_vectors=(vector,))

    assert first.duplicate is False
    assert duplicate.duplicate is True
    assert ledger.count() == 1
    assert first.paper_capital_allowed is False
    assert first.live_allowed is False
    with sqlite3.connect(ledger.path) as connection:
        row = connection.execute(
            "SELECT research_only, paper_capital_allowed, live_allowed, feature_vector_fingerprint FROM shadow_observations"
        ).fetchone()
        assert row == (1, 0, 0, verified_feature_vectors_fingerprint((vector,)))
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM shadow_observations")


def test_shadow_observation_ledger_rejects_unproven_artifact_or_feature_mismatch(tmp_path):
    vector = _vector()
    artifact = _artifact(vector)
    ledger = ShadowObservationLedger(tmp_path / "shadow_observations.sqlite3")

    with pytest.raises(ShadowObservationLedgerError, match="feature fingerprint"):
        ledger.record(
            artifact=artifact,
            observation=_observation(artifact, vector, fingerprint="tampered"),
            feature_vectors=(vector,),
        )
    throttled = _artifact(vector, status="THROTTLED")
    with pytest.raises(ShadowObservationLedgerError, match="not writable"):
        ledger.record(
            artifact=throttled,
            observation=_observation(throttled, vector),
            feature_vectors=(vector,),
        )


def test_batch_target_preview_and_ledgered_shadow_observation_have_exact_parity(tmp_path):
    source_vector, feature_manifest = _canonical_vector(tmp_path, include_manifest=True)
    publication = publish_verified_feature_vectors(
        run_id="shadow_parity_publication",
        feature_snapshot_manifest_path=feature_manifest,
        observed_at=source_vector.observed_at,
        output_dir=tmp_path / "feature_publications",
    )
    vector = load_published_verified_feature_vector(publication.output_path, symbol="BTCEUR", timeframe="5m")
    assert vector.fingerprint == source_vector.fingerprint
    artifact = _artifact(vector)
    available_at = vector.observed_at
    alpha = AlphaSignal(
        strategy_id=artifact.strategy_id,
        strategy_version=artifact.strategy_version,
        signal_id="shadow-parity-signal",
        market=vector.market,
        direction="long",
        generated_at=available_at,
        available_at=available_at,
        feature_versions=dict(vector.feature_snapshot.feature_versions),
        data_snapshot_id=artifact.data_snapshot_id,
        expected_edge_bps=float(vector.values[0].value),
    )
    batch_target = build_target_portfolio((alpha,), decision_id="shadow-parity-decision", decision_at=available_at).target
    preview = preview_runtime_buy_signal(
        symbol="BTC/EUR",
        price=65_000.0,
        signal_timestamp=available_at,
        decision_id="shadow-parity-decision",
        metadata={
            "strategy_id": artifact.strategy_id,
            "strategy_version": artifact.strategy_version,
            "signal_id": alpha.signal_id,
            "data_snapshot_id": artifact.data_snapshot_id,
            "data_available_at": available_at.isoformat(),
            "net_expected_edge_bps": float(vector.values[0].value),
            "shadow_notional_eur": 1.0,
            "feature_versions": dict(vector.feature_snapshot.feature_versions),
            "verified_feature_vectors": {
                vector.feature_snapshot.feature_snapshot_id: verified_feature_vector_to_mapping(vector)
            },
            "strategy_artifact": artifact.to_dict(),
            "market_identity": {
                "exchange": vector.market.exchange,
                "market_type": vector.market.market_type,
                "symbol": vector.market.symbol,
                "base_asset": vector.market.base_asset,
                "quote_asset": vector.market.quote_asset,
            },
        },
    )
    assert preview.status == "SHADOW_PREVIEW_READY"
    assert preview.target_portfolio is not None
    batch_observation = build_shadow_observation_from_target(
        artifact=artifact,
        target_portfolio=batch_target,
        feature_vectors=(vector,),
    )
    shadow_observation = build_shadow_observation_from_target(
        artifact=artifact,
        target_portfolio=preview.target_portfolio,
        feature_vectors=(vector,),
    )
    from autobot.v2.research.shadow_governance import evaluate_shadow_parity

    parity = evaluate_shadow_parity(
        artifact=artifact,
        batch_observation=batch_observation,
        shadow_observation=shadow_observation,
    )
    assert parity.status == "PARITY_OK"
    ledger = ShadowObservationLedger(tmp_path / "shadow_observations.sqlite3")
    recorded = ledger.record(artifact=artifact, observation=shadow_observation, feature_vectors=(vector,))
    assert recorded.duplicate is False
    assert ledger.count() == 1


def test_shadow_observation_ledger_has_no_execution_imports():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/shadow_observation_ledger.py").read_text(encoding="utf-8"))
    forbidden = {
        "autobot.v2.order_router",
        "autobot.v2.paper_trading",
        "autobot.v2.signal_handler_async",
        "autobot.v2.order_executor",
    }
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imports.isdisjoint(forbidden)
