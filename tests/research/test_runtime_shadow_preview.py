from datetime import datetime, timezone

import pytest

from autobot.v2.research.runtime_shadow_preview import preview_runtime_buy_signal
from autobot.v2.research.shadow_governance import StrategyArtifact


pytestmark = pytest.mark.unit


def _metadata(**overrides):
    payload = {
        "strategy_id": "trend_momentum",
        "strategy_version": "trend-v3",
        "data_snapshot_id": "ohlcv_snapshot_1",
        "data_available_at": "2026-07-12T10:01:00+00:00",
        "net_expected_edge_bps": 24.0,
        "shadow_notional_eur": 20.0,
        "feature_versions": {"momentum": "v1", "volatility": "v1"},
        "strategy_artifact": _artifact_payload(),
        "market_identity": {
            "exchange": "kraken",
            "market_type": "spot",
            "symbol": "BTCEUR",
            "base_asset": "BTC",
            "quote_asset": "EUR",
        },
    }
    payload.update(overrides)
    return payload


def _artifact_payload(*, strategy_version: str = "trend-v3") -> dict:
    return StrategyArtifact(
        strategy_id="trend_momentum",
        strategy_version=strategy_version,
        code_commit="preview-fixture-commit",
        data_snapshot_id="ohlcv_snapshot_1",
        feature_versions={"momentum": "v1", "volatility": "v1"},
        parameters={"fixture": True},
        risk_mandate_fingerprint="preview-mandate-fixture",
        validation_manifest_fingerprint="preview-validation-fixture",
        status="SHADOW",
        experiment_id="preview-experiment-fixture",
        experiment_fingerprint="preview-experiment-fingerprint",
        human_approval_reference="preview-human-approval",
    ).to_dict()


def _preview(**metadata):
    return preview_runtime_buy_signal(
        symbol="BTC/EUR",
        price=65_000.0,
        signal_timestamp=datetime(2026, 7, 12, 10, tzinfo=timezone.utc),
        metadata=_metadata(**metadata),
        decision_id="decision-shadow-1",
    )


def test_ready_preview_creates_only_shadow_contracts():
    preview = _preview()

    assert preview.status == "SHADOW_PREVIEW_READY"
    assert preview.alpha_signal is not None
    assert preview.target_portfolio is not None
    assert preview.order_intent is not None
    assert preview.order_intent.execution_mode == "shadow"
    assert preview.risk_decision is not None
    assert preview.risk_decision.approved is False
    assert preview.to_dict()["execution_command_created"] is False
    assert preview.to_dict()["paper_capital_allowed"] is False
    assert preview.to_dict()["live_allowed"] is False


def test_missing_explicit_market_identity_fails_closed():
    preview = _preview(market_identity=None)

    assert preview.status == "SHADOW_PREVIEW_REJECTED"
    assert preview.reason == "market_identity_required"
    assert preview.order_intent is None


def test_ambiguous_symbol_mapping_fails_closed():
    metadata = _metadata()
    metadata["market_identity"] = {**metadata["market_identity"], "symbol": "BTCUSD"}
    preview = _preview(**metadata)

    assert preview.status == "SHADOW_PREVIEW_REJECTED"
    assert preview.reason == "market_identity_symbol_mismatch"


def test_retired_grid_cannot_create_shadow_preview():
    preview = _preview(strategy_id="dynamic_grid")

    assert preview.status == "SHADOW_PREVIEW_REJECTED"
    assert preview.reason == "strategy_runtime_retired"


def test_missing_feature_provenance_is_not_invented():
    preview = _preview(feature_versions={})

    assert preview.status == "SHADOW_PREVIEW_REJECTED"
    assert preview.reason == "feature_versions_required"


def test_shadow_preview_rejects_an_artifact_mismatch():
    preview = _preview(strategy_artifact=_artifact_payload(strategy_version="other"))

    assert preview.status == "SHADOW_PREVIEW_REJECTED"
    assert preview.reason == "strategy_artifact_version_mismatch"
