import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from autobot.v2.api import dashboard
from autobot.v2.pnl_causality_audit import PnlCausalityAuditEngine, PnlCausalityConfig


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
        conn.execute(
            """
            CREATE TABLE orders (
                client_order_id TEXT PRIMARY KEY,
                exchange_order_id TEXT,
                decision_id TEXT,
                signal_id TEXT,
                instance_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                requested_qty REAL NOT NULL,
                filled_qty REAL NOT NULL DEFAULT 0,
                avg_fill_price REAL,
                status TEXT NOT NULL,
                userref INTEGER,
                retries INTEGER NOT NULL DEFAULT 0,
                last_error_code TEXT,
                last_error_message TEXT,
                created_at TEXT NOT NULL,
                sent_at TEXT,
                ack_at TEXT,
                terminal_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        _insert_trade_family(
            conn,
            symbol="TRXEUR",
            position_id="pos-loss",
            instance_id="inst-trx",
            entry_price=0.3000,
            exit_price=0.3010,
            volume=100.0,
            open_fee=0.10,
            close_fee=0.25,
            realized_pnl=-0.25,
            engine="dynamic_grid",
            decision_id="dec-entry-loss",
            created_suffix="10:00:00",
            payload={
                "gross_edge_bps": 135.0,
                "cost_bps": 86.0,
                "net_edge_bps": 49.0,
                "min_edge_bps": 48.0,
                "opportunity": {
                    "regime_context": {"regime": "low_activity", "reason": "low_activity"},
                    "health_context": {"status": "underperforming", "reason": "realized_underperforming"},
                    "atr_context": {"reason": "net_edge_below_adaptive_override"},
                },
            },
        )
        _insert_trade_family(
            conn,
            symbol="ATOMEUR",
            position_id="pos-win",
            instance_id="inst-atom",
            entry_price=5.0,
            exit_price=5.2,
            volume=10.0,
            open_fee=0.05,
            close_fee=0.05,
            realized_pnl=1.9,
            engine="mean_reversion",
            decision_id="dec-entry-win",
            created_suffix="11:00:00",
            payload={
                "gross_edge_bps": 100.0,
                "cost_bps": 20.0,
                "net_edge_bps": 80.0,
                "min_edge_bps": 40.0,
                "opportunity": {
                    "regime_context": {"regime": "range", "reason": "range_stable"},
                    "health_context": {"status": "learning", "reason": "new"},
                },
            },
        )


def _insert_trade_family(
    conn,
    *,
    symbol,
    position_id,
    instance_id,
    entry_price,
    exit_price,
    volume,
    open_fee,
    close_fee,
    realized_pnl,
    engine,
    decision_id,
    created_suffix,
    payload,
    open_slippage_bps=1.0,
    close_slippage_bps=1.0,
):
    opened = f"2026-05-22T{created_suffix}+00:00"
    closed = f"2026-05-22T{str(int(created_suffix[:2]) + 1).zfill(2)}:00:00+00:00"
    conn.execute(
        "INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (position_id, instance_id, symbol, entry_price, volume, "closed", opened, engine, None),
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
            f"open-{position_id}",
            position_id,
            instance_id,
            symbol,
            "buy",
            entry_price,
            entry_price,
            volume,
            open_fee,
            open_slippage_bps,
            None,
            1,
            0,
            None,
            decision_id,
            f"sig-{position_id}",
            "taker",
            opened,
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
            f"close-{position_id}",
            position_id,
            instance_id,
            symbol,
            "sell",
            exit_price,
            exit_price,
            volume,
            close_fee,
            close_slippage_bps,
            realized_pnl,
            0,
            1,
            None,
            f"dec-close-{position_id}",
            f"sig-close-{position_id}",
            "taker",
            closed,
        ),
    )
    conn.execute(
        """
        INSERT INTO decision_ledger (
            event_id, decision_id, signal_id, instance_id, symbol, strategy, engine,
            event_type, event_status, reason, source, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"dlg-{position_id}",
            decision_id,
            f"sig-{position_id}",
            instance_id,
            symbol,
            "grid",
            engine,
            "decision",
            "buy_accepted",
            "all_guards_passed",
            "test",
            json.dumps(payload),
            opened,
        ),
    )
    conn.execute(
        """
        INSERT INTO orders (
            client_order_id, decision_id, signal_id, instance_id, symbol, side, order_type,
            requested_qty, filled_qty, avg_fill_price, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"ord-{position_id}",
            decision_id,
            f"sig-{position_id}",
            instance_id,
            symbol,
            "buy",
            "market",
            volume,
            volume,
            entry_price,
            "FILLED",
            opened,
            opened,
        ),
    )


def _engine() -> PnlCausalityAuditEngine:
    return PnlCausalityAuditEngine(
        PnlCausalityConfig(
            window_hours=720,
            limit=100,
            fee_drag_bps=70.0,
            edge_miss_bps=25.0,
            tiny_notional_eur=10.0,
            weak_profit_factor=0.8,
            min_closed_for_action=1,
        )
    )


def test_pnl_causality_explains_cost_drag_and_edge_miss(tmp_path):
    state_db = tmp_path / "state.db"
    _create_state_db(state_db)

    snapshot = _engine().build_snapshot(state_db_path=str(state_db), paper_mode=True)

    assert snapshot["paper_only_analysis"] is True
    assert snapshot["live_execution_changed"] is False
    assert snapshot["summary"]["closed_trades"] == 2
    assert snapshot["summary"]["net_pnl_eur"] == pytest.approx(1.65)
    loss = next(row for row in snapshot["recent_trades"] if row["symbol"] == "TRXEUR")
    assert loss["verdict"] in {"cost_drag_loss", "edge_model_miss"}
    assert "fees_erased_positive_move" in loss["root_causes"]
    assert "expected_edge_not_realized" in loss["root_causes"]
    assert loss["expected"]["net_edge_bps"] == pytest.approx(49.0)
    assert snapshot["by_symbol"][0]["recommended_action"] in {
        "quarantine_official_paper_until_edge_review",
        "paper_review",
    }


def test_pnl_causality_ignores_closing_legs_without_realized_pnl(tmp_path):
    state_db = tmp_path / "state.db"
    _create_state_db(state_db)
    with sqlite3.connect(state_db) as conn:
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
                "close-without-pnl",
                "pos-no-pnl",
                "inst-no-pnl",
                "XETHZEUR",
                "sell",
                2000.0,
                2001.0,
                0.01,
                0.02,
                5.0,
                None,
                0,
                1,
                None,
                None,
                None,
                "taker",
                "2026-05-22T14:00:00+00:00",
            ),
        )

    snapshot = _engine().build_snapshot(state_db_path=str(state_db), paper_mode=True)

    assert snapshot["summary"]["closed_trades"] == 2
    assert all(row["position_id"] != "pos-no-pnl" for row in snapshot["recent_trades"])


def test_pnl_causality_treats_negative_slippage_as_favorable_not_drag(tmp_path):
    state_db = tmp_path / "state.db"
    _create_state_db(state_db)
    with sqlite3.connect(state_db) as conn:
        _insert_trade_family(
            conn,
            symbol="ETHEUR",
            position_id="pos-favorable-slippage",
            instance_id="inst-eth",
            entry_price=10.0,
            exit_price=10.0,
            volume=10.0,
            open_fee=0.02,
            close_fee=0.02,
            realized_pnl=-0.04,
            engine="mean_reversion",
            decision_id="dec-entry-favorable-slip",
            created_suffix="12:00:00",
            open_slippage_bps=-20.0,
            close_slippage_bps=-30.0,
            payload={
                "gross_edge_bps": 20.0,
                "cost_bps": 10.0,
                "net_edge_bps": 10.0,
                "min_edge_bps": 5.0,
                "opportunity": {
                    "regime_context": {"regime": "range", "reason": "range_stable"},
                    "health_context": {"status": "learning", "reason": "new"},
                },
            },
        )

    snapshot = _engine().build_snapshot(state_db_path=str(state_db), paper_mode=True)

    trade = next((row for row in snapshot["recent_trades"] if row["symbol"] == "ETHEUR"), None)
    assert trade is not None
    assert trade["slippage_bps"] == pytest.approx(0.0)
    assert trade["favorable_slippage_bps"] == pytest.approx(50.0)
    assert trade["absolute_slippage_bps"] == pytest.approx(50.0)
    assert trade["actual_cost_bps"] == pytest.approx(trade["fee_bps"])
    assert "slippage_drag" not in trade["root_causes"]


class _PnlCausalityOrchestrator:
    paper_mode = True

    def __init__(self, db_path):
        self.persistence = SimpleNamespace(db_path=str(db_path))

    def get_status(self):
        return {
            "running": True,
            "websocket_connected": True,
            "instance_count": 1,
            "capital": {"paper_mode": True},
        }

    def get_instances_snapshot(self):
        return [{"id": "inst-trx", "symbol": "TRXEUR", "capital": 100.0}]

    def get_capital_snapshot(self):
        return {"paper_mode": True, "source_status": "ok", "total_capital": 100.0}


def test_pnl_causality_endpoint_returns_audit(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    state_db = tmp_path / "state.db"
    _create_state_db(state_db)

    dashboard.app.state.orchestrator = _PnlCausalityOrchestrator(state_db)
    client = TestClient(dashboard.app)
    response = client.get("/api/pnl-causality", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["closed_trades"] == 2
    assert body["runtime"]["websocket_connected"] is True
    assert body["top_loss_trades"][0]["symbol"] == "TRXEUR"
