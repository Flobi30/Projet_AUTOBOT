import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autobot.v2.api import dashboard


pytestmark = pytest.mark.integration


class _Executor:
    def __init__(self, db_path: Path):
        self.db_path = str(db_path)


class _Orchestrator:
    paper_mode = True

    def __init__(self, db_path: Path):
        self.order_executor = _Executor(db_path)

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
                },
                "last_order": None,
                "warmup": {"active": False},
                "blocked_reasons": [],
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
