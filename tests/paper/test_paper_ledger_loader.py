import sqlite3
from datetime import date

import pytest

from autobot.v2.paper.ledger_loader import load_paper_trades_db_journal, load_state_db_paper_ledger


pytestmark = pytest.mark.unit


def _create_state_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE trade_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT NOT NULL,
                position_id TEXT,
                instance_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                expected_price REAL,
                executed_price REAL NOT NULL,
                volume REAL NOT NULL,
                fees REAL DEFAULT 0,
                slippage_bps REAL,
                realized_pnl REAL,
                is_opening_leg INTEGER DEFAULT 0,
                is_closing_leg INTEGER DEFAULT 0,
                exchange_order_id TEXT,
                decision_id TEXT,
                signal_id TEXT,
                execution_liquidity TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE decision_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                decision_id TEXT,
                signal_id TEXT,
                instance_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy TEXT,
                engine TEXT,
                event_type TEXT NOT NULL,
                event_status TEXT,
                reason TEXT,
                source TEXT NOT NULL,
                payload_json TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def test_state_db_loader_pairs_opening_and_closing_legs(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO decision_ledger
            (event_id, decision_id, signal_id, instance_id, symbol, strategy, engine, event_type,
             event_status, reason, source, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "evt_buy",
                "dec_buy",
                "sig_buy",
                "inst_1",
                "TRXEUR",
                "grid",
                "trend_momentum",
                "decision",
                "buy_accepted",
                "all_guards_passed",
                "signal_handler_runtime",
                '{"side":"buy","regime":"range"}',
                "2026-06-03T08:59:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO decision_ledger
            (event_id, decision_id, signal_id, instance_id, symbol, strategy, engine, event_type,
             event_status, reason, source, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "evt_sell",
                "dec_sell",
                "sig_sell",
                "inst_1",
                "TRXEUR",
                "grid",
                "trend_momentum",
                "decision",
                "sell_accepted",
                "take_profit",
                "signal_handler_runtime",
                '{"side":"sell","regime":"range"}',
                "2026-06-03T09:59:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
             volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
             exchange_order_id, decision_id, signal_id, execution_liquidity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "trd_buy",
                "pos_1",
                "inst_1",
                "TRXEUR",
                "buy",
                1.0,
                1.01,
                100.0,
                0.20,
                5.0,
                None,
                1,
                0,
                "PAPER_BUY",
                "dec_buy",
                "sig_buy",
                "taker",
                "2026-06-03T09:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
             volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
             exchange_order_id, decision_id, signal_id, execution_liquidity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "trd_sell",
                "pos_1",
                "inst_1",
                "TRXEUR",
                "sell",
                1.20,
                1.19,
                100.0,
                0.25,
                6.0,
                17.55,
                0,
                1,
                "PAPER_SELL",
                "dec_sell",
                "sig_sell",
                "taker",
                "2026-06-03T10:00:00+00:00",
            ),
        )

    loaded = load_state_db_paper_ledger(db_path)

    assert loaded.source_type == "state_db_trade_ledger"
    assert loaded.trade_count == 1
    assert loaded.decision_count == 2
    assert loaded.warnings == ()
    trade = loaded.journal.records[0]
    assert trade.strategy_id == "trend_momentum"
    assert trade.symbol == "TRXEUR"
    assert trade.entry_price == pytest.approx(1.01)
    assert trade.exit_price == pytest.approx(1.19)
    assert trade.gross_pnl_eur == pytest.approx(18.0)
    assert trade.net_pnl_eur == pytest.approx(17.55)
    assert trade.fees_eur == pytest.approx(0.45)
    assert trade.slippage_eur == pytest.approx(0.1219)
    assert trade.metadata["slippage"]["adverse_eur"] == pytest.approx(0.1219)
    assert trade.metadata["slippage"]["favorable_eur"] == pytest.approx(0.0)
    assert trade.metadata["slippage"]["opening"]["signed_bps"] == pytest.approx(5.0)
    assert trade.metadata["slippage"]["closing"]["signed_bps"] == pytest.approx(6.0)
    assert trade.metadata["slippage"]["anomaly"] is False
    assert trade.entry_reason == "all_guards_passed"
    assert trade.exit_reason == "take_profit"
    assert trade.regime == "range"


def test_state_db_loader_keeps_favorable_signed_slippage_out_of_costs(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
             volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
             exchange_order_id, decision_id, signal_id, execution_liquidity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "trd_buy",
                "pos_favorable",
                "inst_1",
                "TRXEUR",
                "buy",
                1.0,
                1.0,
                100.0,
                0.20,
                0.0,
                None,
                1,
                0,
                "PAPER_BUY",
                None,
                None,
                "taker",
                "2026-06-03T09:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
             volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
             exchange_order_id, decision_id, signal_id, execution_liquidity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "trd_sell",
                "pos_favorable",
                "inst_1",
                "TRXEUR",
                "sell",
                1.0,
                1.1,
                100.0,
                0.20,
                -150.0,
                9.60,
                0,
                1,
                "PAPER_SELL",
                None,
                None,
                "taker",
                "2026-06-03T10:00:00+00:00",
            ),
        )

    loaded = load_state_db_paper_ledger(db_path)

    assert loaded.trade_count == 1
    assert loaded.warnings == ("slippage_bps_anomaly:pos_favorable",)
    trade = loaded.journal.records[0]
    assert trade.gross_pnl_eur == pytest.approx(10.0)
    assert trade.net_pnl_eur == pytest.approx(9.60)
    assert trade.fees_eur == pytest.approx(0.40)
    assert trade.slippage_eur == pytest.approx(0.0)
    assert trade.metadata["slippage"]["adverse_eur"] == pytest.approx(0.0)
    assert trade.metadata["slippage"]["favorable_eur"] == pytest.approx(1.65)
    assert trade.metadata["slippage"]["closing"]["signed_bps"] == pytest.approx(-150.0)
    assert trade.metadata["slippage"]["anomaly"] is True


def test_state_db_loader_uses_position_strategy_when_decision_link_missing(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE positions (
                id TEXT PRIMARY KEY,
                instance_id TEXT,
                buy_price REAL,
                volume REAL,
                status TEXT,
                open_time TEXT,
                strategy TEXT,
                metadata TEXT,
                symbol TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO positions
            (id, instance_id, buy_price, volume, status, open_time, strategy, metadata, symbol)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "pos_grid",
                "inst_1",
                1.0,
                100.0,
                "closed",
                "2026-06-03T09:00:00+00:00",
                "grid",
                '{"strategy_id":"dynamic_grid"}',
                "TRXEUR",
            ),
        )
        conn.execute(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
             volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
             exchange_order_id, decision_id, signal_id, execution_liquidity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "trd_buy",
                "pos_grid",
                "inst_1",
                "TRXEUR",
                "buy",
                1.0,
                1.0,
                100.0,
                0.2,
                0.0,
                None,
                1,
                0,
                "PAPER_BUY",
                None,
                None,
                "taker",
                "2026-06-03T09:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
             volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
             exchange_order_id, decision_id, signal_id, execution_liquidity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "trd_sell",
                "pos_grid",
                "inst_1",
                "TRXEUR",
                "sell",
                1.1,
                1.1,
                100.0,
                0.2,
                0.0,
                9.6,
                0,
                1,
                "PAPER_SELL",
                None,
                None,
                "taker",
                "2026-06-03T10:00:00+00:00",
            ),
        )

    loaded = load_state_db_paper_ledger(db_path)

    assert loaded.trade_count == 1
    trade = loaded.journal.records[0]
    assert trade.strategy_id == "grid"
    assert trade.metadata["strategy_source"] == "position"
    assert trade.metadata["position"]["strategy"] == "grid"


def test_state_db_loader_filters_report_date_and_flags_missing_opening(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
             volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
             exchange_order_id, decision_id, signal_id, execution_liquidity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "trd_orphan_sell",
                "pos_missing",
                "inst_1",
                "ETHEUR",
                "sell",
                2000.0,
                2010.0,
                0.1,
                0.40,
                4.0,
                0.60,
                0,
                1,
                "PAPER_SELL",
                None,
                None,
                "taker",
                "2026-06-03T11:00:00+00:00",
            ),
        )

    loaded = load_state_db_paper_ledger(db_path, report_date=date(2026, 6, 3))

    assert loaded.trade_count == 1
    assert loaded.warnings == ("opening_leg_missing:pos_missing",)
    assert loaded.journal.records[0].metadata["opening_leg_missing"] is True


def test_state_db_loader_skips_closing_leg_without_realized_pnl(tmp_path):
    db_path = tmp_path / "state.db"
    _create_state_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
             volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
             exchange_order_id, decision_id, signal_id, execution_liquidity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "trd_buy",
                "pos_bad_price",
                "inst_1",
                "XETHZEUR",
                "buy",
                1900.0,
                1900.0,
                0.01,
                0.01,
                0.0,
                None,
                1,
                0,
                "PAPER_BUY",
                None,
                None,
                "taker",
                "2026-06-03T09:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, expected_price, executed_price,
             volume, fees, slippage_bps, realized_pnl, is_opening_leg, is_closing_leg,
             exchange_order_id, decision_id, signal_id, execution_liquidity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "trd_sell_missing_pnl",
                "pos_bad_price",
                "inst_1",
                "XETHZEUR",
                "sell",
                1910.0,
                60000.0,
                0.01,
                0.01,
                -300000.0,
                None,
                0,
                1,
                "PAPER_SELL",
                None,
                None,
                "taker",
                "2026-06-03T10:00:00+00:00",
            ),
        )

    loaded = load_state_db_paper_ledger(db_path)

    assert loaded.trade_count == 0
    assert loaded.warnings == ("realized_pnl_missing:pos_bad_price",)


def test_paper_trades_db_loader_pairs_fills_fifo(tmp_path):
    db_path = tmp_path / "paper_trades.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE trades (
                id TEXT PRIMARY KEY,
                txid TEXT UNIQUE,
                symbol TEXT,
                side TEXT,
                volume REAL,
                price REAL,
                fees REAL,
                timestamp TEXT,
                status TEXT,
                userref INTEGER,
                liquidity TEXT DEFAULT 'unknown',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO trades
            (id, txid, symbol, side, volume, price, fees, timestamp, status, userref, liquidity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("b1", "BUY1", "TRXEUR", "buy", 100.0, 1.0, 0.2, "2026-06-03T09:00:00+00:00", "filled", 1, "taker"),
                ("s1", "SELL1", "TRXEUR", "sell", 100.0, 1.1, 0.2, "2026-06-03T10:00:00+00:00", "filled", 2, "taker"),
            ],
        )

    loaded = load_paper_trades_db_journal(db_path)

    assert loaded.source_type == "paper_trades_db_fifo"
    assert loaded.trade_count == 1
    trade = loaded.journal.records[0]
    assert trade.gross_pnl_eur == pytest.approx(10.0)
    assert trade.net_pnl_eur == pytest.approx(9.6)
    assert trade.fees_eur == pytest.approx(0.4)
