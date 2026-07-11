from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.contracts import AlphaSignal, MarketIdentity
from autobot.v2.research.portfolio_construction import (
    CapacityInput,
    PortfolioConstructionConfig,
    build_target_portfolio,
    estimate_capacity,
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
