from __future__ import annotations

import ast
from datetime import datetime, timezone
import sqlite3
from pathlib import Path

import pytest

from autobot.v2.contracts import (
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
    verified_feature_vectors_fingerprint,
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


def _artifact(vector: VerifiedFeatureVector, *, status: str = "SHADOW_ELIGIBLE") -> StrategyArtifact:
    return StrategyArtifact(
        strategy_id="trend_momentum",
        strategy_version="shadow-observation-v1",
        code_commit="shadow-observation-fixture",
        data_snapshot_id="ohlcv_shadow_observation",
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
    with pytest.raises(ShadowObservationLedgerError, match="not writable"):
        ledger.record(
            artifact=_artifact(vector, status="THROTTLED"),
            observation=_observation(_artifact(vector, status="THROTTLED"), vector),
            feature_vectors=(vector,),
        )


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
