from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from autobot.v2.contracts import (
    AlphaSignal,
    FeatureSnapshotReference,
    MarketIdentity,
    StrategyArtifactReference,
)
from autobot.v2.research.bound_shadow_risk_evidence import (
    BoundShadowRiskEvidenceError,
    build_bound_shadow_risk_evidence,
)
from autobot.v2.research.contract_shadow_pipeline import evaluate_alpha_signal_in_shadow
from autobot.v2.research.backtest_alpha_adapter import cost_model_fingerprint
from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.execution_simulator import (
    PESSIMISTIC_SCENARIO,
    MarketExecutionRules,
    ResearchExecutionConfig,
    ResearchExecutionSimulator,
    ShadowMarketSnapshot,
)
from autobot.v2.research.canonical_microstructure_profile import (
    CanonicalMicrostructureProfileReport,
    CanonicalMicrostructureSymbolProfile,
)
from autobot.v2.research.microstructure_cost_evidence import derive_microstructure_cost_evidence
from autobot.v2.research.portfolio_construction import (
    CapacityObservation,
    build_target_portfolio,
    review_target_portfolio_capacity,
)
from autobot.v2.research.portfolio_sizing import derive_research_sizing_decision
from autobot.v2.research.strategy_risk_mandates import (
    PreTradeAutonomyRequest,
    StrategyHealthSnapshot,
    StrategyRiskMandate,
)


pytestmark = pytest.mark.integration


def _timestamp() -> datetime:
    return datetime(2026, 7, 16, 12, tzinfo=timezone.utc)


def _base_cost_config() -> ExecutionCostConfig:
    return ExecutionCostConfig(
        taker_fee_bps=10.0,
        fallback_spread_bps=8.0,
        slippage_bps=4.0,
        latency_buffer_bps=1.0,
        max_liquidity_participation=0.05,
    )


def _signal(*, expected_edge_bps: float = 25.0) -> AlphaSignal:
    at = _timestamp()
    return AlphaSignal(
        strategy_id="funding_basis",
        strategy_version="v1",
        signal_id="signal-contract-shadow",
        market=MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR"),
        direction="long",
        generated_at=at,
        available_at=at,
        feature_versions={"basis_bps": "1"},
        data_snapshot_id="snapshot-contract-shadow",
        expected_edge_bps=expected_edge_bps,
        metadata={"cost_model_fingerprint": cost_model_fingerprint(_base_cost_config().to_dict())},
    )


def _mandate() -> StrategyRiskMandate:
    return StrategyRiskMandate.from_mapping(
        {
            "mandate_id": "mandate-contract-shadow",
            "strategy_id": "funding_basis",
            "mode_allowed": "shadow",
            "capital_max_eur": 1_000.0,
            "shadow_notional_max_eur": 1_000.0,
            "max_daily_loss_eur": 100.0,
            "max_drawdown_pct": 50.0,
            "max_position_eur": 1_000.0,
            "max_symbol_exposure_eur": 1_000.0,
            "max_total_exposure_eur": 1_000.0,
            "max_trades_per_day": 20,
            "max_orders_per_minute": 10,
            "max_fees_per_day_eur": 100.0,
            "max_slippage_bps": 100.0,
            "max_spread_bps": 100.0,
            "allowed_symbols": ["BTCEUR"],
            "allowed_timeframes": ["1h"],
            "allowed_order_types": ["market"],
            "cooldown_after_losses": 10,
            "rolling_pf_min": 0.1,
            "rolling_expectancy_min": -100.0,
            "min_edge_to_cost_ratio": 1.0,
            "data_freshness_max_seconds": 60,
            "expires_at": "2026-12-31T23:59:59+00:00",
            "human_approved_required_for_risk_increase": True,
            "paper_capital_allowed": False,
            "live_allowed": False,
        }
    )


def _artifact(mandate: StrategyRiskMandate | None = None) -> StrategyArtifactReference:
    mandate = mandate or _mandate()
    return StrategyArtifactReference(
        artifact_id="artifact-contract-shadow",
        fingerprint="artifact-fingerprint-contract-shadow",
        strategy_id="funding_basis",
        strategy_version="v1",
        code_commit="contract-shadow-fixture",
        data_snapshot_id="snapshot-contract-shadow",
        feature_versions={"basis_bps": "1"},
        status="SHADOW",
        feature_snapshots=(
            FeatureSnapshotReference(
                feature_snapshot_id="features-contract-shadow",
                fingerprint="feature-fingerprint-contract-shadow",
                snapshot_kind="FEATURE_SNAPSHOT",
                source_snapshot_id="snapshot-contract-shadow",
                source_snapshot_fingerprint="source-fingerprint-contract-shadow",
                feature_registry_fingerprint="registry-fingerprint-contract-shadow",
                feature_versions={"basis_bps": "1"},
                runtime_parity_proven=True,
                material_verified=True,
                bundle_content_fingerprint="bundle-content-contract-shadow",
            ),
        ),
        risk_mandate=mandate.to_reference(),
    )


def _market_rules() -> dict[MarketIdentity, MarketExecutionRules]:
    return {
        MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR"): MarketExecutionRules(
            "BTCEUR",
            0.0001,
            5.0,
            8,
            1,
            MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR"),
            "kraken-asset-pairs-contract-shadow",
            sha256(b"kraken-asset-pairs-contract-shadow").hexdigest(),
        )
    }


def _simulator() -> ResearchExecutionSimulator:
    return ResearchExecutionSimulator(
        cost_config=_base_cost_config(),
        market_rules=_market_rules(),
    )


def _bound_risk_evidence(
    signal: AlphaSignal,
    artifact: StrategyArtifactReference,
    *,
    capital_eur: float = 1_000.0,
    capacity_observations: dict[str, CapacityObservation] | None = None,
    max_liquidity_participation: float = 0.05,
    health: StrategyHealthSnapshot | None = None,
):
    target = build_target_portfolio((signal,), decision_id="decision-contract-shadow", decision_at=signal.available_at).target
    capacity = review_target_portfolio_capacity(
        target,
        capital_eur=capital_eur,
        observations=capacity_observations or {"BTCEUR": _capacity_observation()},
        expected_markets={signal.market.symbol: signal.market},
        max_liquidity_participation=max_liquidity_participation,
    )
    sizing_decision = derive_research_sizing_decision(
        target=target,
        capacity_review=capacity,
        strategy_artifact=artifact,
        market=signal.market,
    )
    mandate = _mandate()
    request = PreTradeAutonomyRequest(
        strategy_id=signal.strategy_id,
        symbol=signal.market.symbol,
        timeframe="1h",
        order_type="market",
        notional_eur=capacity.target_notionals_eur[signal.market.symbol],
        symbol_exposure_eur=0.0,
        total_exposure_eur=0.0,
        daily_loss_eur=0.0,
        drawdown_pct=0.0,
        trades_today=0,
        orders_last_minute=0,
        fees_today_eur=0.0,
        slippage_bps=1.0,
        spread_bps=1.0,
        estimated_edge_bps=float(signal.expected_edge_bps or 0.0),
        estimated_total_cost_bps=10.0,
        data_age_seconds=0,
        evaluated_at=signal.available_at,
    )
    return build_bound_shadow_risk_evidence(
        decision_id="decision-contract-shadow",
        signal=signal,
        strategy_artifact=artifact,
        target=target,
        capacity_review=capacity,
        sizing_decision=sizing_decision,
        mandate=mandate,
        pre_trade_request=request,
        health=health or StrategyHealthSnapshot(rolling_pf=1.3, rolling_expectancy=0.2),
    )


def _capacity_observation(*, at: datetime | None = None, market: MarketIdentity | None = None) -> CapacityObservation:
    timestamp = at or _timestamp()
    identity = market or MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR")
    return CapacityObservation(
        market=identity,
        source_snapshot_id="microstructure-contract-shadow",
        source_snapshot_fingerprint=sha256(b"microstructure-contract-shadow").hexdigest(),
        event_time=timestamp,
        available_time=timestamp,
        ingestion_time=timestamp,
        observed_liquidity_eur=20_000.0,
    )


def _snapshot(*, seconds: int = 2) -> ShadowMarketSnapshot:
    event_time = _timestamp() + timedelta(seconds=seconds)
    source_snapshot_id = f"contract-shadow-book-{seconds}"
    return ShadowMarketSnapshot(
        market=MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR"),
        event_time=event_time,
        available_time=event_time,
        ingestion_time=event_time,
        source_snapshot_id=source_snapshot_id,
        source_fingerprint=sha256(source_snapshot_id.encode("utf-8")).hexdigest(),
        price=100.0,
        bid=99.95,
        ask=100.05,
        liquidity_eur=20_000.0,
    )


def _cost_evidence():
    profile = CanonicalMicrostructureSymbolProfile(
        symbol="BTCEUR",
        base_asset="BTC",
        quote_asset="EUR",
        sample_count=120,
        distinct_utc_hours=20,
        first_event_time="2026-07-20T00:00:00+00:00",
        last_event_time="2026-07-21T12:00:00+00:00",
        observation_span_seconds=129_600.0,
        median_spread_bps=8.0,
        p75_spread_bps=9.0,
        p95_spread_bps=14.0,
        p99_spread_bps=18.0,
        median_bid_depth_eur=1_000.0,
        median_ask_depth_eur=1_000.0,
        p95_latency_ms=50.0,
        observed_research_spread_bps=9.0,
        observed_stress_spread_bps=18.0,
        calibration_status="RESEARCH_CALIBRATION_READY",
    )
    report = CanonicalMicrostructureProfileReport(
        run_id="contract-shadow-cost-evidence",
        generated_at="2026-07-21T12:00:00+00:00",
        source_paths=("canonical/kraken_spot_microstructure.csv",),
        source_fingerprint=sha256(b"contract-shadow-cost-evidence").hexdigest(),
        raw_row_count=120,
        accepted_row_count=120,
        duplicate_row_count=0,
        rejected_row_count=0,
        status="RESEARCH_CALIBRATION_READY",
        profiles=(profile,),
    )
    return derive_microstructure_cost_evidence(
        report,
        market=MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR"),
        base_cost_config=_base_cost_config(),
    )


def test_contract_shadow_pipeline_requires_all_boundaries_before_shadow_fill():
    signal = _signal()
    artifact = _artifact()
    review = evaluate_alpha_signal_in_shadow(
        signal,
        decision_id="decision-contract-shadow",
        strategy_artifact=artifact,
        capital_eur=1_000.0,
        capacity_observations={"BTCEUR": _capacity_observation()},
        max_liquidity_participation=0.05,
        base_cost_config=_base_cost_config(),
        simulator=_simulator(),
        snapshots=(_snapshot(),),
        risk_evidence=_bound_risk_evidence(signal, artifact),
    )

    assert review.status == "SHADOW_FILLED"
    assert review.target_result is not None
    assert review.capacity_review is not None and review.capacity_review.status == "CAPACITY_OK"
    assert review.scenario_review is not None and review.scenario_review.status == "SCENARIO_EDGE_OK"
    assert review.order_intent is not None and review.order_intent.execution_mode == "shadow"
    assert review.outcome is not None and review.outcome.status == "FILLED"
    assert review.outcome.fill is not None
    assert review.order_intent.metadata["simulation_cost_model_fingerprint"] == cost_model_fingerprint(_base_cost_config().to_dict())
    assert review.outcome.fill.metadata["simulation_cost_model_fingerprint"] == cost_model_fingerprint(_base_cost_config().to_dict())
    assert review.outcome.fill.metadata["simulation_scenario"] == "central"
    assert review.execution_command_created is False
    assert review.paper_capital_allowed is False
    assert review.live_allowed is False


def test_contract_shadow_pipeline_fails_closed_on_stale_capacity_or_provenance_mismatch():
    signal = _signal()
    stale = evaluate_alpha_signal_in_shadow(
        signal,
        decision_id="decision-contract-shadow",
        strategy_artifact=_artifact(),
        capital_eur=1_000.0,
        capacity_observations={
            "BTCEUR": _capacity_observation(at=_timestamp() - timedelta(minutes=3))
        },
        max_liquidity_participation=0.05,
        base_cost_config=_base_cost_config(),
        simulator=_simulator(),
        snapshots=(),
        risk_evidence=None,
    )
    mismatch = evaluate_alpha_signal_in_shadow(
        signal,
        decision_id="decision-contract-shadow",
        strategy_artifact=replace(_artifact(), data_snapshot_id="wrong-snapshot"),
        capital_eur=1_000.0,
        capacity_observations={},
        max_liquidity_participation=0.05,
        base_cost_config=_base_cost_config(),
        simulator=_simulator(),
        snapshots=(),
        risk_evidence=None,
    )

    assert stale.status == "CAPACITY_BLOCKED"
    assert stale.order_intent is None
    assert stale.outcome is None
    assert mismatch.status == "CONTRACT_REJECTED"
    assert mismatch.reason == "strategy_artifact_data_snapshot_mismatch"
    assert mismatch.order_intent is None


def test_contract_shadow_pipeline_rejects_capacity_from_a_different_market_identity():
    signal = _signal()
    review = evaluate_alpha_signal_in_shadow(
        signal,
        decision_id="decision-contract-shadow",
        strategy_artifact=_artifact(),
        capital_eur=1_000.0,
        capacity_observations={
            "BTCEUR": _capacity_observation(
                market=MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "USD")
            )
        },
        max_liquidity_participation=0.05,
        base_cost_config=_base_cost_config(),
        simulator=_simulator(),
        snapshots=(),
        risk_evidence=None,
    )

    assert review.status == "CAPACITY_BLOCKED"
    assert review.reason == "waiting_for_more_data"
    assert review.capacity_review is not None
    assert review.capacity_review.reasons == ("BTCEUR:capacity_market_identity_mismatch",)
    assert review.order_intent is None
    assert review.outcome is None


def test_contract_shadow_pipeline_blocks_missing_or_pessimistic_cost_evidence():
    weak_signal = _signal(expected_edge_bps=5.0)
    blocked = evaluate_alpha_signal_in_shadow(
        weak_signal,
        decision_id="decision-contract-shadow",
        strategy_artifact=_artifact(),
        capital_eur=1_000.0,
        capacity_observations={},
        max_liquidity_participation=0.05,
        base_cost_config=_base_cost_config(),
        simulator=_simulator(),
        snapshots=(),
        risk_evidence=None,
    )

    assert blocked.status == "SCENARIO_BLOCKED"
    assert blocked.reason == "pessimistic_net_edge_not_positive"
    assert blocked.order_intent is None
    assert blocked.scenario_review is not None


def test_contract_shadow_pipeline_rejects_simulator_with_costs_not_derived_from_validated_profile():
    signal = _signal(expected_edge_bps=100.0)
    mismatched_simulator = ResearchExecutionSimulator(
        cost_config=ExecutionCostConfig(
            taker_fee_bps=10.0,
            fallback_spread_bps=8.0,
            slippage_bps=40.0,
            latency_buffer_bps=1.0,
            max_liquidity_participation=0.05,
        ),
        market_rules=_market_rules(),
    )
    review = evaluate_alpha_signal_in_shadow(
        signal,
        decision_id="decision-contract-shadow",
        strategy_artifact=_artifact(),
        capital_eur=1_000.0,
        capacity_observations={},
        max_liquidity_participation=0.05,
        base_cost_config=_base_cost_config(),
        simulator=mismatched_simulator,
        snapshots=(),
        risk_evidence=None,
    )

    assert review.status == "CONTRACT_REJECTED"
    assert review.reason == "simulation_cost_model_fingerprint_mismatch"


def test_contract_shadow_pipeline_allows_an_exact_pessimistic_cost_derivation():
    signal = _signal(expected_edge_bps=100.0)
    artifact = _artifact()
    simulator = ResearchExecutionSimulator(
        cost_config=_base_cost_config(),
        config=ResearchExecutionConfig(scenario=PESSIMISTIC_SCENARIO),
        market_rules=_market_rules(),
    )
    review = evaluate_alpha_signal_in_shadow(
        signal,
        decision_id="decision-contract-shadow",
        strategy_artifact=artifact,
        capital_eur=1_000.0,
        capacity_observations={"BTCEUR": _capacity_observation()},
        max_liquidity_participation=0.05,
        base_cost_config=_base_cost_config(),
        simulator=simulator,
        snapshots=(_snapshot(),),
        risk_evidence=_bound_risk_evidence(signal, artifact),
    )

    assert review.status == "SHADOW_FILLED"
    assert review.outcome is not None and review.outcome.fill is not None
    assert review.outcome.fill.metadata["simulation_scenario"] == "pessimistic"
    assert review.order_intent is not None
    assert review.order_intent.metadata["simulation_cost_model_fingerprint"] == cost_model_fingerprint(
        simulator.cost_config.to_dict()
    )


def test_contract_shadow_pipeline_records_opt_in_microstructure_cost_evidence():
    evidence = _cost_evidence()
    signal = _signal(expected_edge_bps=100.0)
    signal = replace(
        signal,
        metadata={
            "cost_model_fingerprint": evidence.central_cost_model_fingerprint,
            "microstructure_cost_evidence_fingerprint": evidence.evidence_fingerprint,
        },
    )
    simulator = ResearchExecutionSimulator(
        cost_config=evidence.central_cost_config,
        market_rules={
            MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR"): MarketExecutionRules(
                "BTCEUR",
                0.0001,
                5.0,
                8,
                1,
                MarketIdentity("kraken", "spot", "BTCEUR", "BTC", "EUR"),
                "kraken-asset-pairs-contract-shadow-evidence",
                sha256(b"kraken-asset-pairs-contract-shadow-evidence").hexdigest(),
            )
        },
    )
    artifact = _artifact()
    review = evaluate_alpha_signal_in_shadow(
        signal,
        decision_id="decision-contract-shadow",
        strategy_artifact=artifact,
        capital_eur=1_000.0,
        capacity_observations={"BTCEUR": _capacity_observation()},
        max_liquidity_participation=0.05,
        base_cost_config=evidence.central_cost_config,
        microstructure_cost_evidence=evidence,
        simulator=simulator,
        snapshots=(_snapshot(),),
        risk_evidence=_bound_risk_evidence(signal, artifact),
    )

    assert review.status == "SHADOW_FILLED"
    assert review.scenario_review is not None
    assert review.scenario_review.microstructure_cost_evidence_fingerprint == evidence.evidence_fingerprint
    assert review.order_intent is not None
    assert review.order_intent.metadata["microstructure_cost_evidence_fingerprint"] == evidence.evidence_fingerprint
    assert review.execution_command_created is False


def test_contract_shadow_pipeline_rejects_a_manual_approved_risk_decision_without_bound_evidence():
    signal = _signal()
    review = evaluate_alpha_signal_in_shadow(
        signal,
        decision_id="decision-contract-shadow",
        strategy_artifact=_artifact(),
        capital_eur=1_000.0,
        capacity_observations={"BTCEUR": _capacity_observation()},
        max_liquidity_participation=0.05,
        base_cost_config=_base_cost_config(),
        simulator=_simulator(),
        snapshots=(_snapshot(),),
        risk_evidence=None,
    )

    assert review.status == "RISK_EVIDENCE_BLOCKED"
    assert review.reason == "bound_shadow_risk_evidence_missing"
    assert review.order_intent is None
    assert review.outcome is None


def test_contract_shadow_pipeline_rejects_evidence_bound_to_a_different_market():
    signal = _signal()
    artifact = _artifact()
    review = evaluate_alpha_signal_in_shadow(
        signal,
        decision_id="decision-contract-shadow",
        strategy_artifact=artifact,
        capital_eur=1_000.0,
        capacity_observations={"BTCEUR": _capacity_observation()},
        max_liquidity_participation=0.05,
        base_cost_config=_base_cost_config(),
        simulator=_simulator(),
        snapshots=(_snapshot(),),
        risk_evidence=replace(_bound_risk_evidence(signal, artifact), market_symbol="ETHEUR"),
    )

    assert review.status == "RISK_EVIDENCE_BLOCKED"
    assert review.reason == "bound_shadow_risk_evidence_market_symbol_mismatch"
    assert review.order_intent is None
    assert review.outcome is None


def test_bound_shadow_risk_evidence_rejects_a_target_or_gate_mismatch():
    signal = _signal()
    artifact = _artifact()
    evidence = _bound_risk_evidence(signal, artifact)
    target = build_target_portfolio((signal,), decision_id="decision-contract-shadow", decision_at=signal.available_at).target
    capacity = review_target_portfolio_capacity(
        target,
        capital_eur=1_000.0,
        observations={"BTCEUR": _capacity_observation()},
        expected_markets={signal.market.symbol: signal.market},
        max_liquidity_participation=0.05,
    )
    sizing_decision = derive_research_sizing_decision(
        target=target,
        capacity_review=capacity,
        strategy_artifact=artifact,
        market=signal.market,
    )
    with pytest.raises(BoundShadowRiskEvidenceError, match="pre-trade request notional mismatch"):
        build_bound_shadow_risk_evidence(
            decision_id="decision-contract-shadow",
            signal=signal,
            strategy_artifact=artifact,
            target=target,
            capacity_review=capacity,
            sizing_decision=sizing_decision,
            mandate=_mandate(),
            pre_trade_request=replace(evidence.pre_trade_request, notional_eur=evidence.target_notional_eur + 1.0),
        )


def test_bound_shadow_risk_evidence_cannot_cross_a_kill_gate():
    with pytest.raises(BoundShadowRiskEvidenceError, match="gate did not allow shadow review: KILL"):
        _bound_risk_evidence(
            _signal(),
            _artifact(),
            health=StrategyHealthSnapshot(rolling_pf=0.0),
        )


def test_bound_shadow_risk_evidence_does_not_import_runtime_execution_paths():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/bound_shadow_risk_evidence.py").read_text(encoding="utf-8"))
    forbidden = {
        "autobot.v2.portfolio_allocator",
        "autobot.v2.order_router",
        "autobot.v2.signal_handler_async",
        "autobot.v2.paper_trading",
    }
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imports.isdisjoint(forbidden)


def test_contract_shadow_pipeline_does_not_import_runtime_execution_paths():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/contract_shadow_pipeline.py").read_text(encoding="utf-8"))
    forbidden = {"autobot.v2.order_router", "autobot.v2.signal_handler_async", "autobot.v2.paper_trading"}
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imports.isdisjoint(forbidden)
