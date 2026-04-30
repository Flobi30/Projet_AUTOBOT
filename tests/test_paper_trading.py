from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from autobot.v2.paper_trading import PaperTradingExecutor


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
