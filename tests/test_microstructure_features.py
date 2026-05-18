from __future__ import annotations

import pytest

from autobot.v2.modules.order_flow_imbalance import OrderFlowImbalance


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_microstructure_snapshot_exposes_spread_depth_and_risk():
    ofi = OrderFlowImbalance(depth=2)

    await ofi.on_book_update(
        "XBT/EUR",
        {
            "as": [["100.10", "2.0"], ["100.20", "1.0"]],
            "bs": [["100.00", "3.0"], ["99.90", "2.0"]],
        },
    )

    snapshot = ofi.get_snapshot("XXBTZEUR").to_dict()

    assert snapshot["has_book"] is True
    assert snapshot["bid"] == pytest.approx(100.0)
    assert snapshot["ask"] == pytest.approx(100.10)
    assert snapshot["spread_bps"] == pytest.approx(9.995, rel=1e-3)
    assert snapshot["bid_depth_eur"] > snapshot["ask_depth_eur"]
    assert -1.0 <= snapshot["ofi_score"] <= 1.0
    assert 0.0 <= snapshot["buy_adverse_selection_risk"] <= 1.0


@pytest.mark.asyncio
async def test_ofi_signs_match_buy_and_sell_pressure():
    sell_pressure = OrderFlowImbalance(depth=2)
    await sell_pressure.on_book_update(
        "XBT/EUR",
        {"as": [["100.10", "2.0"]], "bs": [["100.00", "2.0"]]},
    )
    await sell_pressure.on_book_update("XBT/EUR", {"a": [["100.05", "3.0"]]})

    buy_pressure = OrderFlowImbalance(depth=2)
    await buy_pressure.on_book_update(
        "XBT/EUR",
        {"as": [["100.10", "2.0"]], "bs": [["100.00", "2.0"]]},
    )
    await buy_pressure.on_book_update("XBT/EUR", {"b": [["100.05", "3.0"]]})

    assert sell_pressure.get_ofi_score("XXBTZEUR") < 0.0
    assert buy_pressure.get_ofi_score("XXBTZEUR") > 0.0


def test_microstructure_unknown_without_book_has_neutral_score():
    snapshot = OrderFlowImbalance().get_snapshot("TRXEUR").to_dict()

    assert snapshot["has_book"] is False
    assert snapshot["reason"] == "book_unavailable"
    assert snapshot["adverse_selection_risk"] == 0.0
