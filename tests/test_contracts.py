from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.contracts import (
    AlphaSignal,
    CanonicalMarketEvent,
    FeatureSnapshotReference,
    FeatureValue,
    LedgerEntry,
    MarketIdentity,
    ExecutionCommand,
    OrderIntent,
    RiskDecision,
    RiskMandateReference,
    StrategyArtifactReference,
    TargetPortfolio,
    contract_fingerprint,
    contract_to_dict,
)

pytestmark = pytest.mark.unit


def _market() -> MarketIdentity:
    return MarketIdentity("Kraken", "spot", "BTCZEUR", "BTC", "EUR")


def _risk_mandate() -> RiskMandateReference:
    return RiskMandateReference(
        mandate_id="research_strategy_shadow_mandate",
        strategy_id="research_strategy",
        fingerprint="risk-mandate-fingerprint-contract-fixture",
        mode_allowed="shadow",
        capital_max_eur=0.0,
        expires_at="2026-12-31T23:59:59+00:00",
        human_approved_required_for_risk_increase=True,
    )


def _artifact_reference() -> StrategyArtifactReference:
    return StrategyArtifactReference(
        artifact_id="strategy_artifact_contract_fixture",
        fingerprint="artifact-fingerprint-contract-fixture",
        strategy_id="research_strategy",
        strategy_version="v1",
        code_commit="contract-fixture-commit",
        data_snapshot_id="snapshot-1",
        feature_versions={"atr": "1"},
        status="SHADOW",
        feature_snapshots=(
            FeatureSnapshotReference(
                feature_snapshot_id="features_contract_fixture",
                fingerprint="feature-fingerprint-contract-fixture",
                snapshot_kind="FEATURE_SNAPSHOT",
                source_snapshot_id="snapshot-1",
                source_snapshot_fingerprint="source-fingerprint-contract-fixture",
                feature_registry_fingerprint="registry-fingerprint-contract-fixture",
                feature_versions={"atr": "1"},
                runtime_parity_proven=True,
            ),
        ),
        risk_mandate=_risk_mandate(),
    )


def test_market_event_enforces_explicit_identity_and_point_in_time_ordering():
    event = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    record = CanonicalMarketEvent(
        market=_market(),
        event_time=event,
        available_time=event + timedelta(seconds=1),
        ingestion_time=event + timedelta(seconds=2),
        source_snapshot_id="ohlcv_snapshot_1",
    )

    assert record.market.quote_asset == "EUR"
    assert record.ingestion_time.tzinfo == timezone.utc

    with pytest.raises(ValueError, match="available_time"):
        CanonicalMarketEvent(
            market=_market(),
            event_time=event,
            available_time=event - timedelta(seconds=1),
            ingestion_time=event,
            source_snapshot_id="bad",
        )


def test_feature_and_signal_reject_lookahead_timestamps():
    event = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="feature available_time"):
        FeatureValue(
            feature_id="atr",
            feature_version="1",
            market=_market(),
            timeframe="1h",
            event_time=event,
            available_time=event - timedelta(seconds=1),
            source_snapshot_id="snapshot",
            value=1.0,
        )

    with pytest.raises(ValueError, match="signal available_at"):
        AlphaSignal(
            strategy_id="research",
            strategy_version="1",
            signal_id="signal-1",
            market=_market(),
            direction="long",
            generated_at=event,
            available_at=event - timedelta(seconds=1),
            feature_versions={"atr": "1"},
            data_snapshot_id="snapshot",
        )


def test_target_portfolio_and_order_intent_keep_risk_boundary_explicit():
    now = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    portfolio = TargetPortfolio(
        decision_id="decision-1",
        generated_at=now,
        target_weights={"BTCZEUR": 0.4},
        reserve_cash_weight=0.6,
    )
    assert portfolio.target_weights["BTCZEUR"] == 0.4

    intent = OrderIntent(
        decision_id="decision-1",
        strategy_id="research_strategy",
        strategy_artifact=_artifact_reference(),
        market=_market(),
        side="buy",
        target_notional=25.0,
        created_at=now,
        data_available_at=now,
        execution_mode="shadow",
        client_order_id="client-1",
    )
    assert intent.execution_mode == "shadow"

    with pytest.raises(ValueError, match="must match"):
        OrderIntent(
            decision_id="decision-1",
            strategy_id="other_strategy",
            strategy_artifact=_artifact_reference(),
            market=_market(),
            side="buy",
            target_notional=25.0,
            created_at=now,
            data_available_at=now,
            execution_mode="shadow",
            client_order_id="client-mismatch",
        )

    missing_feature_evidence = StrategyArtifactReference(
        artifact_id="strategy_artifact_missing_feature_evidence",
        fingerprint="artifact-fingerprint-missing-feature-evidence",
        strategy_id="research_strategy",
        strategy_version="v1",
        code_commit="contract-fixture-commit",
        data_snapshot_id="snapshot-1",
        feature_versions={"atr": "1"},
        status="SHADOW",
        risk_mandate=_risk_mandate(),
    )
    with pytest.raises(ValueError, match="feature snapshot evidence"):
        OrderIntent(
            decision_id="decision-1",
            strategy_id="research_strategy",
            strategy_artifact=missing_feature_evidence,
            market=_market(),
            side="buy",
            target_notional=25.0,
            created_at=now,
            data_available_at=now,
            execution_mode="shadow",
            client_order_id="client-missing-feature-evidence",
        )

    with pytest.raises(ValueError, match="cannot exceed"):
        TargetPortfolio(
            decision_id="bad",
            generated_at=now,
            target_weights={"BTCZEUR": 0.8},
            reserve_cash_weight=0.3,
        )


def test_risk_and_ledger_contracts_require_auditable_rejections():
    now = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="requires at least one reason"):
        RiskDecision(decision_id="decision-1", approved=False, decided_at=now)

    decision = RiskDecision(
        decision_id="decision-1",
        approved=False,
        decided_at=now,
        reasons=("spread_too_wide",),
    )
    entry = LedgerEntry(
        ledger_id="ledger-1",
        entry_type="RISK_REJECTED",
        occurred_at=now,
        strategy_id="research_strategy",
        decision_id=decision.decision_id,
        client_order_id=None,
        source="risk_manager",
        payload={"reasons": list(decision.reasons)},
    )
    assert entry.payload["reasons"] == ["spread_too_wide"]


def test_execution_command_requires_a_risk_boundary_and_contracts_are_stable():
    now = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="risk_decision_id is required"):
        ExecutionCommand(
            command_id="command-1",
            decision_id="decision-1",
            client_order_id="client-1",
            risk_decision_id="",
            issued_at=now,
            execution_mode="paper",
            approved_notional=25,
        )


def test_shadow_contracts_require_immutable_non_authorizing_risk_evidence():
    now = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="risk mandate evidence"):
        StrategyArtifactReference(
            artifact_id="strategy_artifact_missing_risk_mandate",
            fingerprint="artifact-fingerprint-missing-risk-mandate",
            strategy_id="research_strategy",
            strategy_version="v1",
            code_commit="contract-fixture-commit",
            data_snapshot_id="snapshot-1",
            feature_versions={"atr": "1"},
            status="SHADOW",
            feature_snapshots=_artifact_reference().feature_snapshots,
        )
    with pytest.raises(ValueError, match="cannot authorize paper or live"):
        RiskMandateReference(
            mandate_id="invalid-mandate",
            strategy_id="research_strategy",
            fingerprint="invalid-mandate-fingerprint",
            mode_allowed="shadow",
            capital_max_eur=0.0,
            expires_at="2026-12-31T23:59:59+00:00",
            human_approved_required_for_risk_increase=True,
            paper_capital_allowed=True,
        )
    with pytest.raises(ValueError, match="expires_at must be ISO-8601"):
        RiskMandateReference(
            mandate_id="invalid-expiry-mandate",
            strategy_id="research_strategy",
            fingerprint="invalid-expiry-mandate-fingerprint",
            mode_allowed="shadow",
            capital_max_eur=0.0,
            expires_at="not-a-timestamp",
            human_approved_required_for_risk_increase=True,
        )
    assert _artifact_reference().risk_mandate is not None
    assert _artifact_reference().risk_mandate.capital_max_eur == 0.0

    signal = AlphaSignal(
        strategy_id="research_strategy",
        strategy_version="1",
        signal_id="signal-1",
        market=_market(),
        direction="long",
        generated_at=now,
        available_at=now,
        feature_versions={"atr": "1"},
        data_snapshot_id="snapshot-1",
    )
    payload = contract_to_dict(signal)
    assert payload["generated_at"] == "2026-07-10T12:00:00+00:00"
    assert contract_fingerprint(signal) == contract_fingerprint(signal)
