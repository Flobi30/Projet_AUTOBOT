from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from autobot.v2.paper_trading import PaperTradingExecutor
from autobot.v2.order_executor import OrderSide


pytestmark = pytest.mark.unit


def test_paper_symbol_asset_roundtrip_for_altcoins():
    pairs = {
        "XLTCZEUR": "XLTC",
        "XXRPZEUR": "XXRP",
        "XXLMZEUR": "XXLM",
        "SOLEUR": "SOL",
        "TRXEUR": "TRX",
    }

    for symbol, asset in pairs.items():
        assert PaperTradingExecutor._asset_for_symbol(symbol) == asset
        assert PaperTradingExecutor._symbol_for_asset(asset) == symbol


def test_paper_ws_symbol_aliases_match_kraken_subscriptions():
    assert PaperTradingExecutor._ws_symbol_for_symbol("XXBTZEUR") == "XBT/EUR"
    assert PaperTradingExecutor._ws_symbol_for_symbol("XETHZEUR") == "ETH/EUR"
    assert PaperTradingExecutor._ws_symbol_for_symbol("SOLEUR") == "SOL/EUR"


@pytest.mark.asyncio
async def test_paper_market_order_uses_symbol_specific_fallback(tmp_path, monkeypatch):
    executor = PaperTradingExecutor(db_path=str(tmp_path / "paper_trades.db"), initial_capital=1000.0)

    async def no_live_price(_symbol: str):
        return None

    monkeypatch.setattr(executor, "_get_current_price", no_live_price)

    result = await executor.execute_market_order("XETHZEUR", OrderSide.SELL, 0.01, userref=1234)

    assert result.success is True
    assert result.executed_price == pytest.approx(2000.0)
    assert result.fees == pytest.approx(0.01 * 2000.0 * executor.fee_rate)


@pytest.mark.asyncio
async def test_paper_market_order_prefers_signal_price_hint(tmp_path, monkeypatch):
    executor = PaperTradingExecutor(db_path=str(tmp_path / "paper_trades.db"), initial_capital=1000.0)

    async def no_live_price(_symbol: str):
        return None

    monkeypatch.setattr(executor, "_get_current_price", no_live_price)

    result = await executor.execute_market_order(
        "XETHZEUR",
        OrderSide.SELL,
        0.01,
        userref=1234,
        price_hint=1969.53,
    )

    assert result.success is True
    assert result.executed_price == pytest.approx(1969.53)


@pytest.mark.asyncio
async def test_paper_find_order_by_userref(tmp_path, monkeypatch):
    executor = PaperTradingExecutor(db_path=str(tmp_path / "paper_trades.db"), initial_capital=1000.0)

    async def no_live_price(_symbol: str):
        return None

    monkeypatch.setattr(executor, "_get_current_price", no_live_price)
    result = await executor.execute_market_order("XLTCZEUR", OrderSide.BUY, 1.0, userref=9876)

    found = await executor.find_order_by_userref(9876)

    assert found is not None
    txid, order = found
    assert txid == result.txid
    assert order["userref"] == 9876
    assert order["descr"]["pair"] == "XLTCZEUR"


@pytest.mark.asyncio
async def test_trade_balance_uses_asset_specific_fallbacks(tmp_path, monkeypatch):
    executor = PaperTradingExecutor(db_path=str(tmp_path / "paper_trades.db"), initial_capital=1000.0)

    async def no_live_price(_symbol: str):
        return None

    monkeypatch.setattr(executor, "_get_current_price", no_live_price)
    with sqlite3.connect(executor.db_path) as conn:
        conn.execute(
            """
            INSERT INTO trades (id, txid, symbol, side, volume, price, fees, timestamp, status, userref)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "trade-1",
                "PAPER_LMT_ltc",
                "XLTCZEUR",
                "buy",
                1.0,
                100.0,
                0.0,
                datetime.now(timezone.utc).isoformat(),
                "filled",
                None,
            ),
        )
        conn.commit()

    trade_balance = await executor.get_trade_balance("EUR")

    assert trade_balance["equivalent_balance"] == pytest.approx(990.0)
