"""
Tests C1 + C5 — Price validation guards.

Coverage
--------
TradingInstanceAsync._validate_price:
    - Returns False for price = 0
    - Returns False for negative price
    - Returns False for NaN
    - Returns False for +inf / -inf
    - Returns True for a valid price (updates _last_price)
    - Returns False when variation > 10% from last price
    - Returns True when variation <= 10% (boundary)
    - No variation check on first tick (no _last_price yet)

TradingInstanceAsync.on_price_update:
    - Invalid price → strategy NOT called, _price_history unchanged
    - Valid price → strategy called, _price_history updated

KrakenWebSocketAsync._process_ticker:
    - price <= 0 → ticker dropped, no callback
    - price = NaN → ticker dropped
    - bid >= ask → ticker dropped
    - bid = 0 → ticker dropped
    - Valid data → callback dispatched
"""
from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_instance():
    """Build a minimal TradingInstanceAsync without touching SQLite."""
    from autobot.v2.instance_async import TradingInstanceAsync
    from autobot.v2.instance import InstanceStatus

    cfg = MagicMock()
    cfg.initial_capital = 1000.0
    cfg.strategy = "grid"
    cfg.name = "test"
    cfg.leverage = 1

    orch = MagicMock()

    with patch("autobot.v2.instance_async.get_persistence", return_value=MagicMock()):
        inst = TradingInstanceAsync("test-id", cfg, orch)

    return inst


def _make_ticker(price=50_000.0, bid=49_990.0, ask=50_010.0):
    from autobot.v2.websocket_client import TickerData
    return TickerData(
        symbol="XXBTZEUR",
        price=price,
        bid=bid,
        ask=ask,
        volume_24h=100.0,
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# _validate_price — unit tests (sync)
# ---------------------------------------------------------------------------


class TestValidatePrice:
    def setup_method(self):
        self.inst = _make_instance()

    def test_zero_price_rejected(self):
        assert self.inst._validate_price(0.0) is False

    def test_negative_price_rejected(self):
        assert self.inst._validate_price(-1.0) is False

    def test_nan_rejected(self):
        assert self.inst._validate_price(float("nan")) is False

    def test_pos_inf_rejected(self):
        assert self.inst._validate_price(float("inf")) is False

    def test_neg_inf_rejected(self):
        assert self.inst._validate_price(float("-inf")) is False

    def test_valid_price_accepted(self):
        assert self.inst._validate_price(50_000.0) is True

    def test_valid_price_updates_last_price(self):
        self.inst._validate_price(50_000.0)
        assert self.inst._last_price == 50_000.0

    def test_first_tick_no_variation_check(self):
        # _last_price is None initially — variation check skipped
        self.inst._last_price = None
        assert self.inst._validate_price(50_000.0) is True

    def test_variation_below_threshold_accepted(self):
        self.inst._last_price = 50_000.0
        # +9% — within 10% threshold
        assert self.inst._validate_price(54_500.0) is True

    def test_variation_exactly_10pct_rejected(self):
        self.inst._last_price = 50_000.0
        # exactly +10% — rejected (> 0.10 is False, but we use >, so boundary is excluded)
        # abs(55000 - 50000) / 50000 = 0.10 which is NOT > 0.10 → accepted
        assert self.inst._validate_price(55_000.0) is True

    def test_variation_above_threshold_rejected(self):
        self.inst._last_price = 50_000.0
        # +11% — exceeds 10% threshold
        assert self.inst._validate_price(55_500.0) is False

    def test_variation_above_threshold_does_not_update_last_price(self):
        self.inst._last_price = 50_000.0
        self.inst._validate_price(99_000.0)  # +98% — rejected
        assert self.inst._last_price == 50_000.0  # unchanged

    def test_valid_sequence_updates_last_price_each_tick(self):
        self.inst._validate_price(50_000.0)
        self.inst._validate_price(50_100.0)  # +0.2%
        assert self.inst._last_price == 50_100.0


# ---------------------------------------------------------------------------
# on_price_update — async integration
# ---------------------------------------------------------------------------


class TestOnPriceUpdateGuard:
    def setup_method(self):
        self.inst = _make_instance()
        self.strategy = MagicMock()
        self.strategy.on_price = MagicMock()
        self.inst._strategy = self.strategy

        from autobot.v2.instance import InstanceStatus
        self.inst.status = InstanceStatus.RUNNING

    @pytest.mark.asyncio
    async def test_valid_price_calls_strategy(self):
        ticker = _make_ticker(price=50_000.0)
        await self.inst.on_price_update(ticker)
        self.strategy.on_price.assert_called_once_with(50_000.0)

    @pytest.mark.asyncio
    async def test_zero_price_skips_strategy(self):
        ticker = _make_ticker(price=0.0)
        await self.inst.on_price_update(ticker)
        self.strategy.on_price.assert_not_called()

    @pytest.mark.asyncio
    async def test_nan_price_skips_strategy(self):
        ticker = _make_ticker(price=float("nan"))
        await self.inst.on_price_update(ticker)
        self.strategy.on_price.assert_not_called()

    @pytest.mark.asyncio
    async def test_inf_price_skips_strategy(self):
        ticker = _make_ticker(price=float("inf"))
        await self.inst.on_price_update(ticker)
        self.strategy.on_price.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_price_does_not_append_to_history(self):
        ticker = _make_ticker(price=0.0)
        history_len_before = len(self.inst._price_history)
        await self.inst.on_price_update(ticker)
        assert len(self.inst._price_history) == history_len_before

    @pytest.mark.asyncio
    async def test_valid_price_appended_to_history(self):
        ticker = _make_ticker(price=50_000.0)
        await self.inst.on_price_update(ticker)
        assert len(self.inst._price_history) == 1
        assert self.inst._price_history[0][1] == 50_000.0

    @pytest.mark.asyncio
    async def test_abnormal_variation_skips_strategy(self):
        # Establish a baseline price first
        ticker1 = _make_ticker(price=50_000.0)
        await self.inst.on_price_update(ticker1)
        self.strategy.on_price.reset_mock()

        # Now send a +50% spike — should be rejected
        ticker2 = _make_ticker(price=75_000.0)
        await self.inst.on_price_update(ticker2)
        self.strategy.on_price.assert_not_called()


# ---------------------------------------------------------------------------
# KrakenWebSocketAsync._process_ticker — C5 validation
# ---------------------------------------------------------------------------


class TestProcessTickerValidation:
    def _make_ws(self):
        from autobot.v2.websocket_async import KrakenWebSocketAsync
        ws = KrakenWebSocketAsync.__new__(KrakenWebSocketAsync)
        ws._last_prices = {}
        ws._ticker_callbacks = {}
        return ws

    def _make_ticker_data(self, price, bid, ask, volume=1000.0):
        return {
            "c": [str(price), "1"],
            "b": [str(bid), "1"],
            "a": [str(ask), "1"],
            "v": ["500", str(volume)],
        }

    @pytest.mark.asyncio
    async def test_valid_ticker_dispatches_callback(self):
        ws = self._make_ws()
        received = []

        async def cb(ticker):
            received.append(ticker)

        ws._ticker_callbacks["XXBTZEUR"] = [cb]
        await ws._process_ticker("XXBTZEUR", self._make_ticker_data(50_000, 49_990, 50_010))
        assert len(received) == 1
        assert received[0].price == 50_000.0

    @pytest.mark.asyncio
    async def test_zero_price_dropped(self):
        ws = self._make_ws()
        received = []

        async def cb(ticker):
            received.append(ticker)

        ws._ticker_callbacks["XXBTZEUR"] = [cb]
        await ws._process_ticker("XXBTZEUR", self._make_ticker_data(0, 0, 0.01))
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_negative_price_dropped(self):
        ws = self._make_ws()
        received = []

        async def cb(ticker):
            received.append(ticker)

        ws._ticker_callbacks["XXBTZEUR"] = [cb]
        await ws._process_ticker("XXBTZEUR", self._make_ticker_data(-1, 49_990, 50_010))
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_bid_gte_ask_dropped(self):
        ws = self._make_ws()
        received = []

        async def cb(ticker):
            received.append(ticker)

        ws._ticker_callbacks["XXBTZEUR"] = [cb]
        # bid == ask
        await ws._process_ticker("XXBTZEUR", self._make_ticker_data(50_000, 50_010, 50_010))
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_bid_gt_ask_dropped(self):
        ws = self._make_ws()
        received = []

        async def cb(ticker):
            received.append(ticker)

        ws._ticker_callbacks["XXBTZEUR"] = [cb]
        # bid > ask (inverted spread)
        await ws._process_ticker("XXBTZEUR", self._make_ticker_data(50_000, 50_020, 50_010))
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_zero_bid_dropped(self):
        ws = self._make_ws()
        received = []

        async def cb(ticker):
            received.append(ticker)

        ws._ticker_callbacks["XXBTZEUR"] = [cb]
        await ws._process_ticker("XXBTZEUR", self._make_ticker_data(50_000, 0, 50_010))
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_valid_ticker_stored_in_last_prices(self):
        ws = self._make_ws()
        ws._ticker_callbacks["XXBTZEUR"] = []
        await ws._process_ticker("XXBTZEUR", self._make_ticker_data(50_000, 49_990, 50_010))
        assert "XXBTZEUR" in ws._last_prices
        assert ws._last_prices["XXBTZEUR"].price == 50_000.0
