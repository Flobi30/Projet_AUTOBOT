from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.contracts import AlphaSignal, MarketIdentity
from autobot.v2.research.portfolio_construction import (
    CapacityInput,
    CapacityObservation,
    PortfolioConstructionConfig,
    SignalRejection,
    build_target_portfolio,
    estimate_capacity,
    estimate_capacity_curve,
    review_target_portfolio_capacity,
)


pytestmark = pytest.mark.unit


def _signal(
    *,
    signal_id: str,
    symbol: str = "BTCEUR",
    quote: str = "EUR",
    direction: str = "long",
    edge: float | None = 20.0,
    available_offset_seconds: int = 0,
    market_type: str = "spot",
) -> AlphaSignal:
    timestamp = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
    return AlphaSignal(
        strategy_id="funding_basis",
        strategy_version="v1",
        signal_id=signal_id,
        market=MarketIdentity("kraken", market_type, symbol, symbol.replace(quote, ""), quote),
        direction=direction,
        generated_at=timestamp,
        available_at=timestamp + timedelta(seconds=available_offset_seconds),
        feature_versions={"basis_bps": "1.0.0"},
        data_snapshot_id="ohlcv_snapshot",
        expected_edge_bps=edge,
    )


def test_target_portfolio_uses_only_available_long_only_spot_eur_signals():
    now = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
    result = build_target_portfolio(
        (
            _signal(signal_id="good", symbol="BTCEUR", edge=30.0),
            _signal(signal_id="short", direction="short"),
            _signal(signal_id="future", available_offset_seconds=1),
            _signal(signal_id="usd", symbol="BTCUSD", quote="USD"),
            _signal(signal_id="perp", market_type="perpetual"),
        ),
        decision_id="decision-1",
        decision_at=now,
        config=PortfolioConstructionConfig(reserve_cash_weight=0.20, max_symbol_weight=0.35),
    )

    assert result.accepted_signal_ids == ("good",)
    assert result.target.target_weights == {"BTCEUR": pytest.approx(0.35)}
    assert result.target.reserve_cash_weight == pytest.approx(0.65)
    assert result.target.cash_asset == "EUR"
    assert result.target.source_signal_ids == ("good",)
    assert result.target.source_strategy_ids == ("funding_basis",)
    assert result.target.source_data_snapshot_ids == ("ohlcv_snapshot",)
    assert result.target.source_feature_versions == {"basis_bps": "1.0.0"}
    assert {item.reason for item in result.rejected_signals} == {
        "short_not_allowed",
        "signal_not_yet_available",
        "implicit_quote_conversion_not_allowed",
        "non_spot_market_not_allowed",
    }
    assert result.paper_capital_allowed is False
    assert result.live_allowed is False


def test_target_portfolio_caps_turnover_without_inventing_cash_or_weights():
    now = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
    result = build_target_portfolio(
        (_signal(signal_id="btc", symbol="BTCEUR", edge=20.0), _signal(signal_id="eth", symbol="ETHEUR", edge=10.0)),
        decision_id="decision-2",
        decision_at=now,
        current_weights={"XRPEUR": 0.50},
        config=PortfolioConstructionConfig(
            reserve_cash_weight=0.20,
            max_symbol_weight=0.60,
            max_turnover_weight=0.10,
        ),
    )

    assert result.turnover_weight == pytest.approx(0.10)
    assert sum(result.target.target_weights.values()) + result.target.reserve_cash_weight == pytest.approx(1.0)
    assert result.target.target_weights["XRPEUR"] < 0.50
    assert all(weight >= 0.0 for weight in result.target.target_weights.values())


def test_target_portfolio_caps_configured_correlation_group_and_keeps_excess_as_cash():
    now = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
    result = build_target_portfolio(
        (
            _signal(signal_id="btc", symbol="BTCEUR", edge=20.0),
            _signal(signal_id="eth", symbol="ETHEUR", edge=20.0),
            _signal(signal_id="sol", symbol="SOLEUR", edge=20.0),
        ),
        decision_id="correlation-cap",
        decision_at=now,
        config=PortfolioConstructionConfig(
            reserve_cash_weight=0.20,
            max_symbol_weight=0.60,
            max_correlation_group_weight=0.45,
            correlation_groups={"BTCEUR": "CRYPTO_BETA", "ETHEUR": "CRYPTO_BETA", "SOLEUR": "SOL"},
        ),
    )

    beta_weight = result.target.target_weights["BTCEUR"] + result.target.target_weights["ETHEUR"]
    assert beta_weight == pytest.approx(0.45)
    assert result.target.reserve_cash_weight > 0.20
    assert "correlation_group=CRYPTO_BETA" in result.target.rationale["BTCEUR"]


def test_target_portfolio_rejects_conflicting_feature_versions_and_keeps_lineage():
    now = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
    first = _signal(signal_id="first", edge=20.0)
    conflicting = replace(
        _signal(signal_id="second", symbol="ETHEUR", edge=10.0),
        feature_versions={"basis_bps": "2.0.0"},
        data_snapshot_id="other_snapshot",
    )

    result = build_target_portfolio((first, conflicting), decision_id="lineage", decision_at=now)

    assert result.accepted_signal_ids == ("first",)
    assert result.target.source_data_snapshot_ids == ("ohlcv_snapshot",)
    assert result.target.source_feature_versions == {"basis_bps": "1.0.0"}
    assert result.rejected_signals == (SignalRejection("second", "feature_version_conflict:basis_bps"),)


def test_capacity_requires_observed_liquidity_and_enforces_participation_limit():
    waiting = estimate_capacity(CapacityInput("BTCEUR", 100.0), max_liquidity_participation=0.05)
    accepted = estimate_capacity(
        CapacityInput("BTCEUR", 100.0, observed_liquidity_eur=4_000.0), max_liquidity_participation=0.05
    )
    blocked = estimate_capacity(
        CapacityInput("BTCEUR", 250.0, observed_liquidity_eur=4_000.0), max_liquidity_participation=0.05
    )

    assert waiting.status == "WAITING_FOR_MORE_DATA"
    assert accepted.status == "CAPACITY_OK"
    assert accepted.maximum_capacity_eur == pytest.approx(200.0)
    assert blocked.status == "CAPACITY_EXCEEDED"
    assert blocked.paper_capital_allowed is False
    assert blocked.live_allowed is False


def test_capacity_never_treats_historical_volume_as_executable_depth():
    estimate = estimate_capacity(
        CapacityInput("BTCEUR", 100.0, observed_volume_eur=100_000.0),
        max_liquidity_participation=0.05,
    )
    curve = estimate_capacity_curve(
        CapacityInput("BTCEUR", 1.0, observed_volume_eur=100_000.0),
        desired_notionals_eur=(10.0, 100.0),
        max_liquidity_participation=0.05,
    )

    assert estimate.status == "WAITING_FOR_MORE_DATA"
    assert estimate.maximum_capacity_eur is None
    assert estimate.reason == "observed_liquidity_missing_volume_not_executable_depth"
    assert curve.status == "WAITING_FOR_MORE_DATA"
    assert curve.observed_capacity_source is None
    assert all(point.maximum_capacity_eur is None for point in curve.points)


def test_capacity_curve_is_deterministic_and_never_invents_unobserved_depth():
    request = CapacityInput("BTCEUR", 1.0, observed_liquidity_eur=4_000.0)
    curve = estimate_capacity_curve(
        request,
        desired_notionals_eur=(250.0, 50.0, 200.0),
        max_liquidity_participation=0.05,
    )

    assert curve.status == "CAPACITY_EXCEEDED"
    assert curve.observed_capacity_source == "observed_liquidity_eur"
    assert [point.desired_notional_eur for point in curve.points] == [50.0, 200.0, 250.0]
    assert curve.points[0].utilization_ratio == pytest.approx(0.25)
    assert curve.points[1].status == "CAPACITY_OK"
    assert curve.points[2].status == "CAPACITY_EXCEEDED"
    assert curve.paper_capital_allowed is False
    assert curve.live_allowed is False

    missing = estimate_capacity_curve(
        CapacityInput("BTCEUR", 1.0),
        desired_notionals_eur=(10.0, 100.0),
        max_liquidity_participation=0.05,
    )
    assert missing.status == "WAITING_FOR_MORE_DATA"
    assert all(point.maximum_capacity_eur is None for point in missing.points)


def test_target_capacity_review_requires_fresh_point_in_time_observations():
    now = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
    target = build_target_portfolio(
        (_signal(signal_id="btc", edge=20.0),),
        decision_id="decision-capacity",
        decision_at=now,
    ).target

    ready = review_target_portfolio_capacity(
        target,
        capital_eur=1_000.0,
        observations={
            "BTCEUR": CapacityObservation(
                "BTCEUR", observed_liquidity_eur=10_000.0, observed_at=now
            )
        },
        max_liquidity_participation=0.05,
    )
    stale = review_target_portfolio_capacity(
        target,
        capital_eur=1_000.0,
        observations={
            "BTCEUR": CapacityObservation(
                "BTCEUR", observed_liquidity_eur=10_000.0, observed_at=now - timedelta(minutes=3)
            )
        },
        max_liquidity_participation=0.05,
    )
    future = review_target_portfolio_capacity(
        target,
        capital_eur=1_000.0,
        observations={
            "BTCEUR": CapacityObservation(
                "BTCEUR", observed_liquidity_eur=10_000.0, observed_at=now + timedelta(seconds=1)
            )
        },
        max_liquidity_participation=0.05,
    )

    assert ready.status == "CAPACITY_OK"
    assert ready.target_notionals_eur == {"BTCEUR": pytest.approx(350.0)}
    assert ready.paper_capital_allowed is False
    assert ready.live_allowed is False
    assert stale.status == "WAITING_FOR_MORE_DATA"
    assert "BTCEUR:capacity_observation_stale" in stale.reasons
    assert future.status == "WAITING_FOR_MORE_DATA"
    assert "BTCEUR:capacity_observation_after_decision" in future.reasons


def test_target_capacity_review_blocks_any_symbol_that_exceeds_or_lacks_capacity_data():
    now = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
    target = build_target_portfolio(
        (_signal(signal_id="btc", edge=20.0), _signal(signal_id="eth", symbol="ETHEUR", edge=10.0)),
        decision_id="decision-capacity-blocked",
        decision_at=now,
        config=PortfolioConstructionConfig(max_symbol_weight=0.60),
    ).target

    exceeded = review_target_portfolio_capacity(
        target,
        capital_eur=1_000.0,
        observations={
            "BTCEUR": CapacityObservation("BTCEUR", observed_liquidity_eur=1_000.0, observed_at=now),
            "ETHEUR": CapacityObservation("ETHEUR", observed_liquidity_eur=100.0, observed_at=now),
        },
        max_liquidity_participation=0.05,
    )
    missing = review_target_portfolio_capacity(
        target,
        capital_eur=1_000.0,
        observations={"BTCEUR": CapacityObservation("BTCEUR", observed_liquidity_eur=20_000.0, observed_at=now)},
        max_liquidity_participation=0.05,
    )

    assert exceeded.status == "CAPACITY_EXCEEDED"
    assert any(item.symbol == "ETHEUR" and item.status == "CAPACITY_EXCEEDED" for item in exceeded.estimates)
    assert missing.status == "WAITING_FOR_MORE_DATA"
    assert "ETHEUR:capacity_observation_missing" in missing.reasons
