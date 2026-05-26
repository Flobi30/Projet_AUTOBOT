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


@pytest.mark.asyncio
async def test_invalid_book_does_not_create_ofi_block():
    ofi = OrderFlowImbalance(depth=2)
    await ofi.on_book_update(
        "XBT/EUR",
        {
            "as": [["100.00", "2.0"]],
            "bs": [["100.10", "2.0"]],
        },
    )
    await ofi.on_book_update("XBT/EUR", {"a": [["99.95", "4.0"]]})

    snapshot = ofi.get_snapshot("XXBTZEUR").to_dict()

    assert snapshot["has_book"] is False
    assert snapshot["reason"] == "invalid_book"
    assert snapshot["bid"] == pytest.approx(100.10)
    assert snapshot["ask"] == pytest.approx(99.95)
    assert ofi.is_unbalanced_against("XXBTZEUR", "buy") is False


@pytest.mark.asyncio
async def test_order_book_reset_clears_invalid_state_for_recovery():
    ofi = OrderFlowImbalance(depth=2)
    await ofi.on_book_update(
        "XBT/EUR",
        {
            "as": [["100.00", "2.0"]],
            "bs": [["100.10", "2.0"]],
        },
    )
    invalid = ofi.get_quality_snapshot("XXBTZEUR")
    assert invalid["reason"] == "invalid_book"
    assert invalid["invalid_count"] >= 1

    reset = ofi.reset_book("XXBTZEUR", reason="unit_test")
    after = ofi.get_quality_snapshot("XXBTZEUR")

    assert reset["reset"] is True
    assert reset["reset_count"] == 1
    assert after["reason"] == "book_unavailable"
    assert after["invalid_count"] == 0
    assert after["reset_count"] == 1
    assert after["last_reset_reason"] == "unit_test"


@pytest.mark.asyncio
async def test_update_only_messages_are_ignored_until_snapshot_after_reset():
    ofi = OrderFlowImbalance(depth=2)
    await ofi.on_book_update(
        "XBT/EUR",
        {
            "as": [["100.10", "2.0"]],
            "bs": [["100.00", "2.0"]],
        },
    )
    ofi.reset_book("XXBTZEUR", reason="unit_test")

    await ofi.on_book_update("XBT/EUR", {"a": [["99.95", "4.0"]], "b": [["100.10", "2.0"]]})
    awaiting = ofi.get_quality_snapshot("XXBTZEUR")
    assert awaiting["reason"] == "book_unavailable"
    assert awaiting["invalid_count"] == 0

    await ofi.on_book_update(
        "XBT/EUR",
        {
            "as": [["100.10", "2.0"]],
            "bs": [["100.00", "2.0"]],
        },
    )
    recovered = ofi.get_quality_snapshot("XXBTZEUR")
    assert recovered["reason"] == "ok"
    assert recovered["has_book"] is True


@pytest.mark.asyncio
async def test_book_is_kept_to_requested_depth_after_updates():
    ofi = OrderFlowImbalance(depth=2)
    await ofi.on_book_update(
        "XBT/EUR",
        {
            "as": [["100.10", "1.0"], ["100.20", "1.0"]],
            "bs": [["100.00", "1.0"], ["99.90", "1.0"]],
        },
    )

    await ofi.on_book_update(
        "XBT/EUR",
        {
            "a": [["100.30", "5.0"], ["100.40", "5.0"]],
            "b": [["99.80", "5.0"], ["99.70", "5.0"]],
        },
    )

    book = ofi._books["XXBTZEUR"]
    assert list(book["asks"]) == [100.10, 100.20]
    assert list(book["bids"]) == [100.00, 99.90]
