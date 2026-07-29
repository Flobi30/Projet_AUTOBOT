from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from autobot.v2.contracts import AlphaSignal, MarketIdentity
from autobot.v2.research.backtest_alpha_adapter import cost_model_fingerprint
from autobot.v2.research.execution_cost_model import ExecutionCostConfig
from autobot.v2.research.portfolio_construction import CapacityObservation, PortfolioConstructionConfig
from autobot.v2.research.portfolio_shadow_review import (
    PortfolioShadowReviewError,
    review_portfolio_in_shadow,
)


pytestmark = pytest.mark.unit


def _at() -> datetime:
    return datetime(2026, 7, 29, 12, tzinfo=timezone.utc)


def _market(symbol: str) -> MarketIdentity:
    return MarketIdentity("kraken", "spot", symbol, symbol.removesuffix("EUR"), "EUR")


def _cost_config() -> ExecutionCostConfig:
    return ExecutionCostConfig(
        taker_fee_bps=10.0,
        fallback_spread_bps=8.0,
        slippage_bps=4.0,
        latency_buffer_bps=1.0,
        max_liquidity_participation=0.05,
    )


def _signal(*, signal_id: str, symbol: str, edge: float = 80.0) -> AlphaSignal:
    timestamp = _at()
    return AlphaSignal(
        strategy_id="funding_basis",
        strategy_version="v1",
        signal_id=signal_id,
        market=_market(symbol),
        direction="long",
        generated_at=timestamp,
        available_at=timestamp,
        feature_versions={"basis_bps": "1.0.0"},
        data_snapshot_id="portfolio-shadow-snapshot",
        expected_edge_bps=edge,
        metadata={"cost_model_fingerprint": cost_model_fingerprint(_cost_config().to_dict())},
    )


def _capacity(symbol: str, *, liquidity_eur: float | None = 20_000.0) -> CapacityObservation:
    timestamp = _at()
    source_snapshot_id = f"portfolio-shadow-{symbol.lower()}"
    return CapacityObservation(
        market=_market(symbol),
        source_snapshot_id=source_snapshot_id,
        source_snapshot_fingerprint=sha256(source_snapshot_id.encode("utf-8")).hexdigest(),
        event_time=timestamp,
        available_time=timestamp,
        ingestion_time=timestamp,
        observed_liquidity_eur=liquidity_eur,
    )


def _review(signals: tuple[AlphaSignal, ...], **overrides):
    arguments = {
        "decision_id": "portfolio-shadow-decision",
        "decision_at": _at(),
        "capital_eur": 1_000.0,
        "capacity_observations": {"BTCEUR": _capacity("BTCEUR"), "ETHEUR": _capacity("ETHEUR")},
        "max_liquidity_participation": 0.05,
        "base_cost_config": _cost_config(),
    }
    arguments.update(overrides)
    return review_portfolio_in_shadow(
        signals,
        **arguments,
    )


def test_multi_signal_review_is_deterministic_and_remains_non_executable():
    btc = _signal(signal_id="btc", symbol="BTCEUR")
    eth = _signal(signal_id="eth", symbol="ETHEUR")

    first = _review((eth, btc))
    second = _review((btc, eth))

    assert first.status == "PORTFOLIO_SHADOW_READY"
    assert first.reason == "all_target_components_survive_pessimistic_cost_and_capacity_review"
    assert first.input_signal_ids == ("btc", "eth")
    assert first.accepted_signal_ids == ("btc", "eth")
    assert first.target_result is not None
    assert first.target_result.target.target_weights == second.target_result.target.target_weights
    assert tuple(review.signal_id for review in first.scenario_reviews) == ("btc", "eth")
    assert all(review.pessimistic_passed for review in first.scenario_reviews)
    assert first.capacity_review is not None
    assert first.capacity_review.status == "CAPACITY_OK"
    assert first.research_only is True
    assert first.paper_capital_allowed is False
    assert first.live_allowed is False


def test_review_blocks_the_whole_target_when_any_accepted_signal_fails_pessimistic_costs():
    btc = _signal(signal_id="btc", symbol="BTCEUR")
    eth = _signal(signal_id="eth", symbol="ETHEUR", edge=3.0)

    review = _review((btc, eth))

    assert review.status == "SCENARIO_BLOCKED"
    assert review.reason == "eth:pessimistic_net_edge_not_positive"
    assert review.target_result is not None
    assert review.capacity_review is None
    assert {item.signal_id for item in review.scenario_reviews} == {"btc", "eth"}


def test_review_fails_closed_when_capacity_is_missing_for_one_target_exposure():
    btc = _signal(signal_id="btc", symbol="BTCEUR")
    eth = _signal(signal_id="eth", symbol="ETHEUR")

    review = _review(
        (btc, eth),
        capacity_observations={"BTCEUR": _capacity("BTCEUR")},
    )

    assert review.status == "CAPACITY_BLOCKED"
    assert review.reason == "waiting_for_more_data"
    assert review.capacity_review is not None
    assert review.capacity_review.status == "WAITING_FOR_MORE_DATA"
    assert "ETHEUR:capacity_observation_missing" in review.capacity_review.reasons


def test_review_applies_correlation_cap_before_reviewing_all_selected_exposures():
    btc = _signal(signal_id="btc", symbol="BTCEUR")
    eth = _signal(signal_id="eth", symbol="ETHEUR")

    review = _review(
        (btc, eth),
        portfolio_config=PortfolioConstructionConfig(
            reserve_cash_weight=0.20,
            max_symbol_weight=0.60,
            max_correlation_group_weight=0.35,
            correlation_groups={"BTCEUR": "CRYPTO_BETA", "ETHEUR": "CRYPTO_BETA"},
        ),
    )

    assert review.status == "PORTFOLIO_SHADOW_READY"
    assert review.target_result is not None
    weights = review.target_result.target.target_weights
    assert weights["BTCEUR"] + weights["ETHEUR"] == pytest.approx(0.35)
    assert review.target_result.target.reserve_cash_weight == pytest.approx(0.65)


def test_review_rejects_duplicate_signal_ids_before_target_construction():
    btc = _signal(signal_id="same", symbol="BTCEUR")
    duplicate = replace(_signal(signal_id="same", symbol="ETHEUR"), strategy_id="other_strategy")

    with pytest.raises(PortfolioShadowReviewError, match="unique signal_id"):
        _review((btc, duplicate))


def test_review_module_has_no_execution_or_runtime_path_imports_or_constructors():
    source_path = Path("src/autobot/v2/research/portfolio_shadow_review.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    forbidden_modules = {
        "autobot.v2.order_router",
        "autobot.v2.paper_trading",
        "autobot.v2.signal_handler_async",
        "autobot.v2.orchestrator_async",
        "autobot.v2.order_executor",
        "autobot.v2.order_executor_async",
    }
    assert not (imported_modules & forbidden_modules)
    constructed = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not ({"OrderIntent", "OrderEvent", "FillEvent", "ExecutionCommand"} & constructed)
