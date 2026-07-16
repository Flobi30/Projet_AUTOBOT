import pytest

from autobot.v2.research.execution_cost_model import (
    ExecutionCostConfig,
    ExecutionCostModel,
    FillRequest,
)


pytestmark = pytest.mark.unit


def test_execution_cost_model_applies_fees_spread_slippage_and_latency():
    model = ExecutionCostModel(
        ExecutionCostConfig(
            taker_fee_bps=16.0,
            fallback_spread_bps=10.0,
            slippage_bps=5.0,
            latency_buffer_bps=1.0,
            min_notional_eur=5.0,
        )
    )

    fill = model.simulate_fill(FillRequest(symbol="TRXEUR", side="buy", price=1.0, notional_eur=100.0))

    assert model.config.to_dict()["taker_fee_bps"] == pytest.approx(16.0)
    assert fill.accepted is True
    assert fill.reason == "filled"
    assert fill.execution_price > fill.requested_price
    assert round(fill.fee_eur, 4) == 0.16
    assert round(fill.spread_cost_eur, 4) == 0.05
    assert round(fill.slippage_eur, 4) == 0.05
    assert round(fill.latency_cost_eur, 4) == 0.01
    assert round(fill.effective_cost_bps, 1) == 27.0


def test_execution_cost_model_rejects_small_or_illiquid_orders():
    model = ExecutionCostModel(ExecutionCostConfig(min_notional_eur=10.0, max_liquidity_participation=0.05))

    small = model.simulate_fill(FillRequest(symbol="TRXEUR", side="buy", price=1.0, notional_eur=5.0))
    illiquid = model.simulate_fill(
        FillRequest(symbol="TRXEUR", side="buy", price=1.0, notional_eur=100.0, liquidity_eur=1000.0)
    )

    assert small.accepted is False
    assert small.reason == "below_min_notional"
    assert illiquid.accepted is False
    assert illiquid.reason == "insufficient_liquidity"


def test_execution_cost_model_respects_limit_price():
    model = ExecutionCostModel(ExecutionCostConfig(fallback_spread_bps=20.0, slippage_bps=10.0))

    fill = model.simulate_fill(
        FillRequest(symbol="XXBTZEUR", side="buy", price=100.0, notional_eur=50.0, order_type="limit", limit_price=100.0)
    )

    assert fill.accepted is False
    assert fill.reason == "limit_price_not_reached"


def test_round_trip_pnl_is_net_of_fees_and_uses_execution_prices():
    model = ExecutionCostModel(ExecutionCostConfig(taker_fee_bps=10.0, fallback_spread_bps=0.0, slippage_bps=0.0, latency_buffer_bps=0.0))
    entry = model.simulate_fill(FillRequest(symbol="TRXEUR", side="buy", price=1.0, quantity=100.0))
    exit_fill = model.simulate_fill(FillRequest(symbol="TRXEUR", side="sell", price=1.1, quantity=100.0))

    pnl = model.round_trip_pnl(entry, exit_fill)

    assert round(pnl.gross_pnl_eur, 4) == 10.0
    assert round(pnl.fees_eur, 4) == 0.21
    assert round(pnl.net_pnl_eur, 4) == 9.79


def test_round_trip_pnl_deducts_all_modeled_execution_costs():
    model = ExecutionCostModel(
        ExecutionCostConfig(
            taker_fee_bps=10.0,
            fallback_spread_bps=8.0,
            slippage_bps=5.0,
            latency_buffer_bps=2.0,
        )
    )
    entry = model.simulate_fill(FillRequest(symbol="TRXEUR", side="buy", price=1.0, quantity=100.0))
    exit_fill = model.simulate_fill(FillRequest(symbol="TRXEUR", side="sell", price=1.1, quantity=100.0))

    pnl = model.round_trip_pnl(entry, exit_fill)

    assert pnl.total_cost_eur > pnl.fees_eur
    assert pnl.net_pnl_eur == pytest.approx(pnl.gross_pnl_eur - pnl.total_cost_eur)
