import sqlite3
import asyncio
from pathlib import Path

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
