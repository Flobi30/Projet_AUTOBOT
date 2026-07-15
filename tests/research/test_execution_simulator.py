from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.contracts import MarketIdentity, OrderIntent, StrategyArtifactReference
from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.execution_simulator import (
    PESSIMISTIC_SCENARIO,
    MarketExecutionRules,
    ResearchExecutionConfig,
    ResearchExecutionSimulator,
    ShadowMarketSnapshot,
)


pytestmark = pytest.mark.unit


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


def _snapshot(*, seconds: int = 2, liquidity: float | None = 4_000.0) -> ShadowMarketSnapshot:
    return ShadowMarketSnapshot(
        timestamp=datetime(2026, 7, 11, 12, tzinfo=timezone.utc) + timedelta(seconds=seconds),
        price=100.0,
        bid=99.95,
        ask=100.05,
        liquidity_eur=liquidity,
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
            "BTCEUR": MarketExecutionRules(
                symbol="BTCEUR",
                min_volume=0.0001,
                min_notional_eur=5.0,
                volume_decimals=8,
                price_decimals=1,
            )
        },
    )


def test_shadow_simulator_records_partial_fill_and_is_idempotent():
    simulator = _simulator()
    intent = _intent(notional=300.0)
    first = simulator.simulate(intent, (_snapshot(),))
    replay = simulator.simulate(intent, (_snapshot(),))

    assert first.status == "PARTIALLY_FILLED"
    assert first.filled_notional_eur == pytest.approx(200.0)
    assert first.unfilled_notional_eur == pytest.approx(100.0)
    assert first.fill is not None and first.fill_event is not None
    assert first.order_events[-1].event_type == "PARTIALLY_FILLED"
    assert replay is first
    assert first.paper_capital_allowed is False
    assert first.live_allowed is False


def test_shadow_simulator_expires_without_a_timely_market_and_rejects_non_shadow():
    expired = _simulator().simulate(_intent(), ())
    stale = _simulator().simulate(_intent(notional=101.0), (_snapshot(seconds=180),))
    paper = _simulator().simulate(_intent(mode="paper"), (_snapshot(),))

    assert expired.status == "EXPIRED"
    assert expired.order_events[-1].event_type == "CANCELLED"
    assert expired.reason == "no_market_after_latency"
    assert stale.status == "EXPIRED"
    assert stale.reason == "market_data_stale_before_fill"
    assert paper.status == "REJECTED"
    assert paper.reason == "non_shadow_intent_not_allowed"


def test_shadow_simulator_requires_explicit_market_rules_and_uses_cached_kraken_precision():
    no_rules = ResearchExecutionSimulator(
        cost_config=ExecutionCostConfig(min_notional_eur=5.0, max_liquidity_participation=0.05),
    ).simulate(_intent(notional=100.0), (_snapshot(),))
    rules = MarketExecutionRules.from_kraken_asset_pair(
        symbol="BTCEUR",
        payload={"ordermin": "0.0001", "costmin": "5", "lot_decimals": 8, "pair_decimals": 1},
    )

    assert no_rules.status == "REJECTED"
    assert no_rules.reason == "market_execution_rules_missing"
    assert rules.symbol == "BTCEUR"
    assert rules.volume_decimals == 8


def test_pessimistic_scenario_costs_more_and_restart_recovery_is_deterministic():
    intent = _intent(notional=100.0)
    snapshots = (_snapshot(),)
    central = _simulator().simulate(intent, snapshots)
    pessimistic = _simulator(config=ResearchExecutionConfig(scenario=PESSIMISTIC_SCENARIO)).simulate(intent, snapshots)
    recovered = _simulator().recover(intent, snapshots)

    assert central.status == "FILLED"
    assert pessimistic.status == "FILLED"
    assert pessimistic.fill is not None and central.fill is not None
    assert pessimistic.fill.total_cost_eur > central.fill.total_cost_eur
    assert recovered == central


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
