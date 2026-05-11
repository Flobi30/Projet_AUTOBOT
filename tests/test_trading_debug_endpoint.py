import sqlite3
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from autobot.v2.api import dashboard
from autobot.v2.global_kill_switch import GlobalKillSwitchStore
from autobot.v2.kill_switch import KillSwitch


pytestmark = pytest.mark.integration


def _range_price_history(start: float = 100.0):
    return [{"timestamp": f"2026-04-28T00:{i:02d}:00+00:00", "price": start + (i % 6) * 0.02} for i in range(60)]


class _Executor:
    def __init__(self, db_path: Path):
        self.db_path = str(db_path)


class _Orchestrator:
    paper_mode = True

    def __init__(self, db_path: Path, kill_store=None):
        self.order_executor = _Executor(db_path)
        self._global_kill_store = kill_store or GlobalKillSwitchStore(str(db_path.parent / "global_kill_switch.db"))
        self._instances = {}

    def get_status(self):
        return {
            "running": True,
            "websocket_connected": True,
            "capital": {"paper_mode": True},
        }

    def get_instances_snapshot(self):
        return [
            {
                "id": "inst-eth",
                "name": "ETH paper",
                "symbol": "ETHEUR",
                "status": "running",
                "last_price": 1955.72,
                "last_market_tick": {
                    "timestamp": "2026-04-28T00:59:00+00:00",
                    "symbol": "ETHEUR",
                    "price": 1955.72,
                },
                "last_signal": {
                    "timestamp": "2026-04-28T01:00:00+00:00",
                    "event": "signal_received",
                    "symbol": "ETHEUR",
                    "side": "buy",
                    "price": 1955.72,
                },
                "last_decision": {
                    "timestamp": "2026-04-28T01:00:01+00:00",
                    "event": "buy_rejected",
                    "reason": "cost_guard",
                    "symbol": "ETHEUR",
                    "blocking_condition": "net_edge_bps < adaptive_min_edge_bps",
                    "net_edge_bps": -31.5,
                    "min_edge_bps": 48.5,
                    "atr_pct": 0.001,
                    "edge_context": {"volatility_component_bps": 2.5},
                },
                "last_order": None,
                "warmup": {"active": False},
                "blocked_reasons": [],
                "price_history_tail": _range_price_history(1955.0),
                "runtime_events": [
                    {
                        "timestamp": "2026-04-28T01:00:01+00:00",
                        "event": "buy_rejected",
                        "reason": "cost_guard",
                        "symbol": "ETHEUR",
                        "side": "buy",
                        "blocking_condition": "net_edge_bps < adaptive_min_edge_bps",
                        "net_edge_bps": -31.5,
                        "min_edge_bps": 48.5,
                        "atr_pct": 0.001,
                        "edge_context": {"volatility_component_bps": 2.5},
                    }
                ],
            }
        ]


class _StoppedOrchestrator(_Orchestrator):
    def get_instances_snapshot(self):
        instances = super().get_instances_snapshot()
        for inst in instances:
            inst["status"] = "stopped"
        return instances


class _OrchestratorWithState(_Orchestrator):
    def __init__(self, paper_db_path: Path, state_db_path: Path):
        super().__init__(paper_db_path)
        self.persistence = SimpleNamespace(db_path=str(state_db_path))

    def get_status(self):
        status = super().get_status()
        status["capital"] = {
            "paper_mode": True,
            "source": "paper",
            "source_status": "ok",
            "total_capital": 800.0,
            "available_cash": 700.0,
            "open_position_notional": 100.0,
            "total_profit": -3.0,
        }
        return status


def _init_paper_db(db_path: Path):
    conn = sqlite3.connect(db_path)
    try:
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _init_state_db(db_path: Path):
    conn = sqlite3.connect(db_path)
    try:
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
            INSERT INTO positions
            (id, instance_id, symbol, buy_price, volume, status, open_time, strategy, metadata)
            VALUES
            ('pos-open-eth', 'inst-eth', 'XETHZEUR', 2000.0, 0.01, 'open', '2026-05-10T00:00:00+00:00', 'grid', '{"symbol":"XETHZEUR"}'),
            ('pos-open-legacy', 'inst-legacy', NULL, 100.0, 0.2, 'open', '2026-05-09T00:00:00+00:00', 'grid', '{}'),
            ('pos-closed', 'inst-eth', 'XETHZEUR', 1990.0, 0.01, 'closed', '2026-05-08T00:00:00+00:00', 'grid', '{"symbol":"XETHZEUR"}')
            """
        )
        conn.execute(
            """
            INSERT INTO trade_ledger
            (trade_id, position_id, instance_id, symbol, side, executed_price, volume, fees, realized_pnl, is_opening_leg, is_closing_leg, created_at)
            VALUES
            ('open-legacy', 'pos-open-legacy', 'inst-legacy', 'ADAEUR', 'buy', 100.0, 0.2, 0.01, NULL, 1, 0, '2026-05-09T00:00:00+00:00'),
            ('close-eth', 'pos-closed', 'inst-eth', 'XETHZEUR', 'sell', 2010.0, 0.01, 0.02, 0.18, 0, 1, '2026-05-10T01:00:00+00:00')
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_trading_debug_explains_cost_guard_rejection(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    db_path = tmp_path / "paper_trades.db"
    _init_paper_db(db_path)
    dashboard.app.state.orchestrator = _Orchestrator(db_path)
    client = TestClient(dashboard.app)

    response = client.get("/api/trading/debug", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["overall"]["status"] == "rejected"
    assert body["overall"]["reason"] == "cost_guard"
    assert body["overall"]["blocking_condition"] == "net_edge_bps < adaptive_min_edge_bps"
    assert body["pipeline"]["signal"]["generated"] is True
    assert body["pipeline"]["execution"]["reached"] is False
    assert body["pipeline"]["paper_trade"]["filled_trade_count"] == 0
    assert body["regime"]["symbols"][0]["symbol"] == "ETHEUR"
    assert body["instances"][0]["regime"]["symbol"] == "ETHEUR"
    assert body["cost_edge_model"]["recent_decisions"][0]["atr_bps"] == pytest.approx(10.0)


def test_runtime_trace_reports_tripped_kill_switch(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    db_path = tmp_path / "paper_trades.db"
    _init_paper_db(db_path)
    kill_store = GlobalKillSwitchStore(str(tmp_path / "global_kill_switch.db"))
    kill_store.trip("api_failures", "10 consecutive API failures")
    dashboard.app.state.orchestrator = _Orchestrator(db_path, kill_store)
    client = TestClient(dashboard.app)

    response = client.get("/api/runtime/trace", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["overall_status"] == "critical"
    assert body["safety"]["kill_switch"]["tripped"] is True
    assert body["safety"]["kill_switch"]["reason_code"] == "api_failures"
    assert any(check["name"] == "kill_switch" and check["ok"] is False for check in body["checks"])


def test_runtime_trace_reports_stopped_strategies_as_critical(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    db_path = tmp_path / "paper_trades.db"
    _init_paper_db(db_path)
    dashboard.app.state.orchestrator = _StoppedOrchestrator(db_path)
    client = TestClient(dashboard.app)

    response = client.get("/api/runtime/trace", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["overall_status"] == "critical"
    assert body["strategies"]["active_count"] == 0
    assert body["strategies"]["configured_count"] == 1
    assert body["strategies"]["inactive_count"] == 1
    assert any(check["name"] == "strategy_runtime" and check["ok"] is False for check in body["checks"])
    assert any("aucune strategie ne tourne" in message for message in body["messages"])


def test_positions_audit_endpoint_summarizes_open_positions(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    paper_db_path = tmp_path / "paper_trades.db"
    state_db_path = tmp_path / "autobot_state.db"
    _init_paper_db(paper_db_path)
    _init_state_db(state_db_path)
    dashboard.app.state.orchestrator = _OrchestratorWithState(paper_db_path, state_db_path)
    client = TestClient(dashboard.app)

    response = client.get("/api/positions/audit", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["paper_mode"] is True
    assert body["audit"]["status"] == "ok"
    assert body["audit"]["totals"]["positions"] == 3
    assert body["audit"]["totals"]["open_positions"] == 2
    assert body["audit"]["totals"]["closed_positions"] == 1
    assert body["audit"]["totals"]["realized_pnl"] == pytest.approx(0.18)
    open_by_symbol = {row["symbol"]: row for row in body["audit"]["open_by_symbol"]}
    assert open_by_symbol["XETHZEUR"]["open_positions"] == 1
    assert open_by_symbol["ADAEUR"]["open_positions"] == 1


def test_performance_persisted_awaits_trade_ledger_metrics(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")

    class _Persistence:
        async def get_trade_ledger_metrics(self):
            return {
                "closed_trades": 12,
                "profit_factor": 1.23,
                "expectancy_eur": 0.08,
            }

    monkeypatch.setattr("autobot.v2.persistence.get_persistence", lambda: _Persistence())
    client = TestClient(dashboard.app)

    response = client.get("/api/performance/persisted", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "trade_ledger"
    assert body["metrics"]["closed_trades"] == 12
    assert body["metrics"]["profit_factor"] == pytest.approx(1.23)


def test_acknowledge_kill_switch_clears_paper_runtime_handlers(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    db_path = tmp_path / "paper_trades.db"
    _init_paper_db(db_path)
    kill_store = GlobalKillSwitchStore(str(tmp_path / "global_kill_switch.db"))
    kill_switch = KillSwitch(global_store=kill_store)
    asyncio.run(kill_switch.trigger("api_failures", "10 consecutive API failures"))
    orchestrator = _Orchestrator(db_path, kill_store)
    orchestrator._instances = {
        "inst-eth": type("Inst", (), {"_signal_handler": type("Handler", (), {"_kill_switch": kill_switch})()})()
    }
    dashboard.app.state.orchestrator = orchestrator
    client = TestClient(dashboard.app)

    response = client.post(
        "/api/kill-switch/acknowledge",
        json={"confirmation": "ACKNOWLEDGE_PAPER_KILL_SWITCH", "operator_id": "test"},
        headers={"Authorization": "Bearer tok"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["acknowledged"] is True
    assert body["acknowledged_handlers"] == 1
    assert body["kill_switch"]["tripped"] is False
    assert body["kill_switch"]["reason_code"] is None
    assert body["kill_switch"]["last_trip"]["reason_code"] == "api_failures"
    assert kill_store.get().tripped is False
    assert kill_switch.tripped is False
