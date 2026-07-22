from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from autobot.v2.contracts import (
    FeatureSnapshotReference,
    MarketIdentity,
    OrderIntent,
    RiskDecision,
    RiskMandateReference,
    StrategyArtifactReference,
)
from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.execution_simulator import (
    PESSIMISTIC_SCENARIO,
    MarketExecutionRules,
    ResearchExecutionConfig,
    ResearchExecutionSimulator,
    ShadowMarketSnapshot,
)


pytestmark = pytest.mark.unit


def _risk_mandate() -> RiskMandateReference:
    return RiskMandateReference(
        mandate_id="funding_basis_shadow_mandate",
        strategy_id="funding_basis",
        fingerprint="risk-mandate-fingerprint-execution-fixture",
        mode_allowed="shadow",
        capital_max_eur=0.0,
        shadow_notional_max_eur=1_000.0,
        expires_at="2026-12-31T23:59:59+00:00",
        human_approved_required_for_risk_increase=True,
    )


def _intent(*, mode: str = "shadow", notional: float = 300.0) -> OrderIntent:
    timestamp = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
    return OrderIntent(
        decision_id="decision-1",
        strategy_id="funding_basis",
        strategy_artifact=StrategyArtifactReference(
            artifact_id="strategy_artifact_execution_fixture",
            fingerprint="artifact-fingerprint-execution-fixture",
            strategy_id="funding_basis",
            strategy_version="v1",
            code_commit="execution-fixture-commit",
            data_snapshot_id="snapshot-1",
            feature_versions={"basis_bps": "1"},
            status="SHADOW",
            feature_snapshots=(
                FeatureSnapshotReference(
                    feature_snapshot_id="features_execution_fixture",
                    fingerprint="feature-fingerprint-execution-fixture",
                    snapshot_kind="FEATURE_SNAPSHOT",
                    source_snapshot_id="snapshot-1",
                    source_snapshot_fingerprint="source-fingerprint-execution-fixture",
                feature_registry_fingerprint="registry-fingerprint-execution-fixture",
                feature_versions={"basis_bps": "1"},
                runtime_parity_proven=True,
                material_verified=True,
                bundle_content_fingerprint="bundle-content-execution-fixture",
            ),
            ),
            risk_mandate=_risk_mandate(),
        ),
        market=MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR"),
        side="buy",
        target_notional=notional,
        created_at=timestamp,
        data_available_at=timestamp,
        execution_mode=mode,
        client_order_id=f"shadow-{mode}-{notional}",
        metadata={"requested_price": 100.0, "order_type": "market"},
    )


def _market() -> MarketIdentity:
    return MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR")


def _snapshot(
    *,
    seconds: int = 2,
    liquidity: float | None = 4_000.0,
    market: MarketIdentity | None = None,
    available_delay_seconds: int = 0,
    ingestion_delay_seconds: int = 0,
    source_suffix: str = "default",
) -> ShadowMarketSnapshot:
    event_time = datetime(2026, 7, 11, 12, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    available_time = event_time + timedelta(seconds=available_delay_seconds)
    ingestion_time = available_time + timedelta(seconds=ingestion_delay_seconds)
    source_identity = f"shadow-snapshot-{seconds}-{available_delay_seconds}-{ingestion_delay_seconds}-{source_suffix}"
    return ShadowMarketSnapshot(
        market=market or _market(),
        event_time=event_time,
        available_time=available_time,
        ingestion_time=ingestion_time,
        source_snapshot_id=source_identity,
        source_fingerprint=sha256(source_identity.encode("utf-8")).hexdigest(),
        price=100.0,
        bid=99.95,
        ask=100.05,
        liquidity_eur=liquidity,
    )


def _risk_decision(
    intent: OrderIntent,
    *,
    approved: bool = True,
    decision_id: str | None = None,
    reduced_notional: float | None = None,
) -> RiskDecision:
    return RiskDecision(
        decision_id=decision_id or intent.decision_id,
        approved=approved,
        decided_at=intent.created_at,
        reasons=() if approved else ("risk_fixture_rejected",),
        reduced_notional=reduced_notional,
    )


def _simulator(*, config: ResearchExecutionConfig | None = None) -> ResearchExecutionSimulator:
    return ResearchExecutionSimulator(
        cost_config=ExecutionCostConfig(
            taker_fee_bps=16.0,
            fallback_spread_bps=8.0,
            slippage_bps=4.0,
            latency_buffer_bps=1.0,
            min_notional_eur=5.0,
            max_liquidity_participation=0.05,
        ),
        config=config or ResearchExecutionConfig(),
        market_rules={
            _market(): MarketExecutionRules(
                symbol="BTCEUR",
                min_volume=0.0001,
                min_notional_eur=5.0,
                volume_decimals=8,
                price_decimals=1,
                market=_market(),
                source_snapshot_id="kraken-asset-pairs-fixture",
                source_fingerprint=sha256(b"kraken-asset-pairs-fixture").hexdigest(),
            )
        },
    )


def test_shadow_simulator_records_partial_fill_and_is_idempotent():
    simulator = _simulator()
    intent = _intent(notional=300.0)
    risk = _risk_decision(intent)
    first = simulator.simulate(intent, (_snapshot(),), risk_decision=risk)
    replay = simulator.simulate(intent, (_snapshot(),), risk_decision=risk)

    assert first.status == "PARTIALLY_FILLED"
    assert first.filled_notional_eur == pytest.approx(200.0)
    assert first.unfilled_notional_eur == pytest.approx(100.0)
    assert first.fill is not None and first.fill_event is not None
    assert first.order_events[-1].event_type == "PARTIALLY_FILLED"
    assert replay is first
    assert first.paper_capital_allowed is False
    assert first.live_allowed is False


def test_shadow_simulator_expires_without_a_timely_market_and_rejects_non_shadow():
    expired_intent = _intent()
    stale_intent = _intent(notional=101.0)
    paper_intent = _intent(mode="paper")
    expired = _simulator().simulate(expired_intent, (), risk_decision=_risk_decision(expired_intent))
    stale = _simulator().simulate(stale_intent, (_snapshot(seconds=180),), risk_decision=_risk_decision(stale_intent))
    paper = _simulator().simulate(paper_intent, (_snapshot(),), risk_decision=_risk_decision(paper_intent))

    assert expired.status == "EXPIRED"
    assert expired.order_events[-1].event_type == "CANCELLED"
    assert expired.reason == "no_market_after_latency"
    assert stale.status == "EXPIRED"
    assert stale.reason == "market_data_stale_before_fill"
    assert paper.status == "REJECTED"
    assert paper.reason == "non_shadow_intent_not_allowed"


def test_shadow_simulator_requires_explicit_market_rules_and_uses_cached_kraken_precision():
    intent = _intent(notional=100.0)
    no_rules = ResearchExecutionSimulator(
        cost_config=ExecutionCostConfig(min_notional_eur=5.0, max_liquidity_participation=0.05),
    ).simulate(intent, (_snapshot(),), risk_decision=_risk_decision(intent))
    rules = MarketExecutionRules.from_kraken_asset_pair(
        market=_market(),
        payload={"ordermin": "0.0001", "costmin": "5", "lot_decimals": 8, "pair_decimals": 1},
        source_snapshot_id="kraken-asset-pairs-cached-fixture",
        source_fingerprint=sha256(b"kraken-asset-pairs-cached-fixture").hexdigest(),
    )

    assert no_rules.status == "REJECTED"
    assert no_rules.reason == "market_execution_rules_missing"
    assert rules.symbol == "BTCEUR"
    assert rules.volume_decimals == 8


def test_shadow_simulator_rejects_symbol_only_market_rule_mappings():
    rules = MarketExecutionRules(
        symbol="BTCEUR",
        min_volume=0.0001,
        min_notional_eur=5.0,
        volume_decimals=8,
        price_decimals=1,
        market=_market(),
        source_snapshot_id="kraken-asset-pairs-symbol-only",
        source_fingerprint=sha256(b"kraken-asset-pairs-symbol-only").hexdigest(),
    )

    with pytest.raises(ValueError, match="market_rules keys must be MarketIdentity"):
        ResearchExecutionSimulator(
            cost_config=ExecutionCostConfig(),
            market_rules={"BTCEUR": rules},  # type: ignore[dict-item]
        )


def test_pessimistic_scenario_costs_more_and_restart_recovery_is_deterministic():
    intent = _intent(notional=100.0)
    snapshots = (_snapshot(),)
    risk = _risk_decision(intent)
    central = _simulator().simulate(intent, snapshots, risk_decision=risk)
    pessimistic = _simulator(config=ResearchExecutionConfig(scenario=PESSIMISTIC_SCENARIO)).simulate(
        intent, snapshots, risk_decision=risk
    )
    recovered = _simulator().recover(intent, snapshots, risk_decision=risk)

    assert central.status == "FILLED"
    assert pessimistic.status == "FILLED"
    assert pessimistic.fill is not None and central.fill is not None
    assert pessimistic.fill.total_cost_eur > central.fill.total_cost_eur
    assert recovered == central


def test_shadow_simulator_requires_matching_approved_risk_and_never_increases_notional():
    intent = _intent(notional=100.0)
    missing = _simulator().simulate(intent, (_snapshot(),), risk_decision=None)
    denied = _simulator().simulate(intent, (_snapshot(),), risk_decision=_risk_decision(intent, approved=False))
    mismatch = _simulator().simulate(intent, (_snapshot(),), risk_decision=_risk_decision(intent, decision_id="other"))
    reduced = _simulator().simulate(intent, (_snapshot(),), risk_decision=_risk_decision(intent, reduced_notional=50.0))
    increased = _simulator().simulate(intent, (_snapshot(),), risk_decision=_risk_decision(intent, reduced_notional=101.0))

    assert missing.reason == "risk_decision_missing"
    assert denied.reason == "risk_decision_not_approved"
    assert mismatch.reason == "risk_decision_intent_mismatch"
    assert reduced.status == "FILLED"
    assert reduced.requested_notional_eur == pytest.approx(50.0)
    assert reduced.approved_notional_eur == pytest.approx(50.0)
    assert reduced.risk_decision_id is not None
    assert increased.reason == "risk_decision_increases_requested_notional"


def test_shadow_simulator_rejects_reused_client_order_id_with_changed_intent_or_risk():
    simulator = _simulator()
    intent = _intent(notional=100.0)
    risk = _risk_decision(intent)
    original = simulator.simulate(intent, (_snapshot(),), risk_decision=risk)
    changed_intent = replace(intent, target_notional=101.0)
    changed_risk = _risk_decision(intent, reduced_notional=50.0)

    assert original.status == "FILLED"
    assert simulator.simulate(changed_intent, (_snapshot(),), risk_decision=_risk_decision(changed_intent)).reason == "idempotency_conflict"
    assert simulator.simulate(intent, (_snapshot(),), risk_decision=changed_risk).reason == "idempotency_conflict"


def test_shadow_simulator_rejects_reused_client_order_id_with_changed_market_evidence():
    simulator = _simulator()
    intent = _intent(notional=100.0)
    risk = _risk_decision(intent)
    original = simulator.simulate(intent, (_snapshot(source_suffix="first"),), risk_decision=risk)
    changed_market_evidence = simulator.simulate(intent, (_snapshot(source_suffix="second"),), risk_decision=risk)

    assert original.status == "FILLED"
    assert changed_market_evidence.reason == "idempotency_conflict"


def test_shadow_simulator_canonicalizes_equivalent_snapshot_sequence_order():
    simulator = _simulator()
    intent = _intent(notional=100.0)
    risk = _risk_decision(intent)
    first = _snapshot(seconds=4, source_suffix="first")
    second = _snapshot(seconds=2, source_suffix="second")

    original = simulator.simulate(intent, (first, second), risk_decision=risk)
    replay = simulator.simulate(intent, (second, first), risk_decision=risk)

    assert original.status == "FILLED"
    assert replay is original


def test_shadow_simulator_rejects_cross_market_snapshot_and_uses_ingestion_time():
    intent = _intent(notional=100.0)
    risk = _risk_decision(intent)
    mismatch = _simulator().simulate(
        intent,
        (_snapshot(market=MarketIdentity("kraken", "spot", "BTCUSD", "BTC", "USD")),),
        risk_decision=risk,
    )
    delayed = _simulator().simulate(
        intent,
        (_snapshot(seconds=2, ingestion_delay_seconds=180, source_suffix="late-ingestion"),),
        risk_decision=risk,
    )

    assert mismatch.status == "REJECTED"
    assert mismatch.reason == "market_snapshot_market_identity_mismatch"
    assert delayed.status == "EXPIRED"
    assert delayed.reason == "market_data_stale_before_fill"


def test_shadow_simulator_records_full_market_snapshot_provenance_on_fill():
    intent = _intent(notional=100.0)
    outcome = _simulator().simulate(intent, (_snapshot(),), risk_decision=_risk_decision(intent))

    assert outcome.status == "FILLED"
    assert outcome.fill is not None
    provenance = outcome.fill.metadata["market_snapshot"]
    assert provenance["market"]["symbol"] == "BTCEUR"
    assert provenance["event_time"] == "2026-07-11T12:00:02+00:00"
    assert outcome.market_snapshot_fingerprint == provenance["snapshot_fingerprint"]
    assert outcome.market_snapshot_sequence_fingerprint is not None


def test_shadow_market_boundaries_reject_invalid_provenance_and_rule_market_mismatch():
    event_time = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="available_time cannot precede event_time"):
        ShadowMarketSnapshot(
            market=_market(),
            event_time=event_time,
            available_time=event_time - timedelta(seconds=1),
            ingestion_time=event_time,
            source_snapshot_id="invalid-ordering",
            source_fingerprint=sha256(b"invalid-ordering").hexdigest(),
            price=100.0,
        )
    with pytest.raises(ValueError, match="symbol must match MarketIdentity.symbol"):
        MarketExecutionRules(
            symbol="BTCEUR",
            min_volume=0.0001,
            min_notional_eur=5.0,
            volume_decimals=8,
            price_decimals=1,
            market=MarketIdentity("kraken", "spot", "BTCUSD", "BTC", "USD"),
            source_snapshot_id="invalid-market-rules",
            source_fingerprint=sha256(b"invalid-market-rules").hexdigest(),
        )


def test_shadow_simulator_uses_post_latency_market_price_not_signal_metadata_price():
    intent = replace(_intent(notional=100.0), metadata={"requested_price": 1.0, "order_type": "market"})
    outcome = _simulator().simulate(intent, (_snapshot(),), risk_decision=_risk_decision(intent))

    assert outcome.status == "FILLED"
    assert outcome.fill is not None
    assert outcome.fill.requested_price == pytest.approx(100.0)


def test_block3_research_modules_do_not_import_runtime_order_paths():
    root = Path(__file__).resolve().parents[2]
    forbidden = {"autobot.v2.order_router", "autobot.v2.signal_handler_async", "autobot.v2.order_executor_async"}
    for relative in (
        "src/autobot/v2/research/portfolio_construction.py",
        "src/autobot/v2/research/execution_simulator.py",
    ):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
        assert imports.isdisjoint(forbidden), relative
