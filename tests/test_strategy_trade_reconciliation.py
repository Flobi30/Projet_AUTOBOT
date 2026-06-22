import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from autobot.v2.api import dashboard
from autobot.v2.strategy_trade_reconciliation import (
    StrategyTradeReconciliationConfig,
    StrategyTradeReconciliationEngine,
)


pytestmark = pytest.mark.integration


def _create_state_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE positions (
                id TEXT PRIMARY KEY,
                instance_id TEXT NOT NULL,
                symbol TEXT,
                buy_price REAL NOT NULL,
                volume REAL NOT NULL,
                status TEXT DEFAULT 'open',
                open_time TEXT NOT NULL,
                strategy TEXT,
                metadata TEXT
            )
            """
        )
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
            "INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "pos-trx-1",
                "inst-trx",
                "TRXEUR",
                0.3000,
                100.0,
                "closed",
                "2026-05-22T09:00:00+00:00",
                "dynamic_grid",
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO trade_ledger (
                trade_id, position_id, instance_id, symbol, side, expected_price,
                executed_price, volume, fees, slippage_bps, realized_pnl,
                is_opening_leg, is_closing_leg, exchange_order_id, decision_id,
                signal_id, execution_liquidity, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "close-trx-1",
                "pos-trx-1",
                "inst-trx",
                "TRXEUR",
                "sell",
                0.2980,
                0.2980,
                100.0,
                0.10,
                1.0,
                -0.30,
                0,
                1,
                None,
                "decision-1",
                "signal-1",
                "maker",
                "2026-05-22T10:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO trade_ledger (
                trade_id, position_id, instance_id, symbol, side, expected_price,
                executed_price, volume, fees, slippage_bps, realized_pnl,
                is_opening_leg, is_closing_leg, exchange_order_id, decision_id,
                signal_id, execution_liquidity, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "close-new-1",
                "pos-new-1",
                "inst-new",
                "NEWEUR",
                "sell",
                1.00,
                1.00,
                10.0,
                0.03,
                1.0,
                -0.05,
                0,
                1,
                None,
                "decision-2",
                "signal-2",
                "maker",
                "2026-05-22T10:05:00+00:00",
            ),
        )


def _create_setup_shadow_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE setup_shadow_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                variant TEXT NOT NULL,
                position_id TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                volume REAL NOT NULL,
                notional REAL NOT NULL,
                fees REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                reason TEXT,
                opened_at TEXT,
                closed_at TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO setup_shadow_trades (
                symbol, variant, position_id, entry_price, exit_price, volume,
                notional, fees, realized_pnl, reason, opened_at, closed_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "TRXEUR",
                "grid_wide",
                "shadow-trx-1",
                0.3000,
                0.3060,
                100.0,
                30.60,
                0.03,
                0.57,
                "take_profit",
                "2026-05-22T09:00:00+00:00",
                "2026-05-22T10:20:00+00:00",
                "2026-05-22T10:20:00+00:00",
            ),
        )


def _engine() -> StrategyTradeReconciliationEngine:
    return StrategyTradeReconciliationEngine(
        StrategyTradeReconciliationConfig(
            window_hours=240,
            official_limit=20,
            shadow_limit=20,
            match_tolerance_minutes=60,
            fee_delta_bps_warn=8.0,
            return_delta_bps_warn=20.0,
        )
    )


def test_trade_reconciliation_excludes_retired_grid_shadow_source(tmp_path):
    state_db = tmp_path / "state.db"
    shadow_db = tmp_path / "setup_shadow_lab.db"
    _create_state_db(state_db)
    _create_setup_shadow_db(shadow_db)

    snapshot = _engine().build_snapshot(
        state_db_path=str(state_db),
        paper_mode=True,
        shadow_db_paths={"dynamic_grid": str(shadow_db)},
    )

    assert snapshot["paper_only"] is True
    assert snapshot["live_promotion_allowed"] is False
    assert snapshot["summary"]["official_closes_loaded"] == 0
    assert snapshot["summary"]["matched_count"] == 0
    assert "dynamic_grid" not in snapshot["data_sources"]["shadow"]
    assert snapshot["summary"]["no_match_count"] == 0
    assert snapshot["summary"]["official_loss_shadow_win_count"] == 0
    assert snapshot["rows"] == []


class _TradeReconOrchestrator:
    paper_mode = True

    def __init__(self, state_db):
        self.persistence = SimpleNamespace(db_path=str(state_db))

    def get_status(self):
        return {
            "running": True,
            "instance_count": 1,
            "websocket_connected": True,
            "capital": {
                "paper_mode": True,
                "source": "paper",
                "source_status": "ok",
                "total_capital": 800.0,
            },
        }

    def get_instances_snapshot(self):
        return [{"id": "inst-trx", "symbol": "TRXEUR", "capital": 800.0}]


def test_strategy_trade_reconciliation_endpoint_is_paper_only(monkeypatch, tmp_path):
    state_db = tmp_path / "state.db"
    shadow_db = tmp_path / "setup_shadow_lab.db"
    _create_state_db(state_db)
    _create_setup_shadow_db(shadow_db)
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("SETUP_SHADOW_DB_PATH", str(shadow_db))
    monkeypatch.setenv("TREND_SHADOW_DB_PATH", str(tmp_path / "trend_shadow_lab.db"))
    monkeypatch.setenv("MEAN_REVERSION_SHADOW_DB_PATH", str(tmp_path / "mean_reversion_shadow_lab.db"))
    dashboard.app.state.orchestrator = _TradeReconOrchestrator(state_db)
    client = TestClient(dashboard.app)

    response = client.get("/api/strategy-reconciliation/trades", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "paper"
    assert body["paper_only"] is True
    assert body["live_promotion_allowed"] is False
    assert body["summary"]["matched_count"] == 0
    assert "dynamic_grid" not in body["data_sources"]["shadow"]
    assert body["runtime"]["websocket_connected"] is True
