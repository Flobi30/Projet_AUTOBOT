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


def test_fill_request_rejects_inconsistent_quantity_and_notional():
    with pytest.raises(ValueError, match="quantity and notional_eur must match"):
        FillRequest(symbol="TRXEUR", side="buy", price=2.0, quantity=10.0, notional_eur=100.0)


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


def test_round_trip_pnl_applies_price_impact_once_and_commission_once():
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
    assert pnl.execution_shortfall_eur == pytest.approx(
        pnl.spread_cost_eur + pnl.slippage_eur + pnl.latency_cost_eur
    )
    assert pnl.net_pnl_eur == pytest.approx(pnl.gross_pnl_eur - pnl.fees_eur)
    assert pnl.reference_gross_pnl_eur - pnl.net_pnl_eur == pytest.approx(pnl.total_cost_eur)


@pytest.mark.parametrize(
    ("entry_side", "entry_price", "exit_side", "exit_price"),
    (("buy", 1.0, "sell", 1.1), ("sell", 1.1, "buy", 1.0)),
)
def test_round_trip_cost_attribution_is_consistent_for_both_directions(
    entry_side: str,
    entry_price: float,
    exit_side: str,
    exit_price: float,
):
    model = ExecutionCostModel(
        ExecutionCostConfig(taker_fee_bps=10.0, fallback_spread_bps=8.0, slippage_bps=5.0, latency_buffer_bps=2.0)
    )
    entry = model.simulate_fill(FillRequest(symbol="TRXEUR", side=entry_side, price=entry_price, quantity=100.0))
    exit_fill = model.simulate_fill(FillRequest(symbol="TRXEUR", side=exit_side, price=exit_price, quantity=100.0))

    pnl = model.round_trip_pnl(entry, exit_fill)

    assert pnl.execution_shortfall_eur == pytest.approx(
        pnl.spread_cost_eur + pnl.slippage_eur + pnl.latency_cost_eur
    )
    assert pnl.reference_gross_pnl_eur - pnl.net_pnl_eur == pytest.approx(pnl.total_cost_eur)


def test_round_trip_pnl_rejects_an_exit_that_does_not_close_the_entry():
    model = ExecutionCostModel()
    entry = model.simulate_fill(FillRequest(symbol="TRXEUR", side="buy", price=1.0, quantity=10.0))
    wrong_exit = model.simulate_fill(FillRequest(symbol="TRXEUR", side="buy", price=1.1, quantity=10.0))

    with pytest.raises(ValueError, match="must close the entry side"):
        model.round_trip_pnl(entry, wrong_exit)


def test_round_trip_pnl_rejects_partial_close_until_position_ledger_owns_allocation():
    model = ExecutionCostModel()
    entry = model.simulate_fill(FillRequest(symbol="TRXEUR", side="buy", price=1.0, quantity=10.0))
    partial_exit = model.simulate_fill(FillRequest(symbol="TRXEUR", side="sell", price=1.1, quantity=5.0))

    with pytest.raises(ValueError, match="requires matched quantities"):
        model.round_trip_pnl(entry, partial_exit)
