import pytest
from fastapi.testclient import TestClient

from autobot.v2.api import dashboard
from autobot.v2.colony_manager import ColonyConfig, ColonyManager


pytestmark = pytest.mark.integration


class _Orchestrator:
    paper_mode = True

    def get_status(self):
        return {
            "running": True,
            "instance_count": 2,
            "websocket_connected": True,
            "capital": {
                "paper_mode": True,
                "source": "paper",
                "source_status": "ok",
                "total_capital": 1000.0,
                "total_balance": 1000.0,
            },
        }

    def get_instances_snapshot(self):
        return [
            {
                "id": "inst-btc",
                "name": "Grid BTC",
                "symbol": "XXBTZEUR",
                "capital": 500.0,
                "profit": 8.0,
                "profit_pct": 1.6,
                "max_drawdown": 0.02,
                "open_positions": 0,
                "warmup": {"active": False},
                "blocked_reasons": [],
                "last_signal": {"symbol": "XXBTZEUR", "side": "buy", "price": 65000},
                "last_decision": {
                    "symbol": "XXBTZEUR",
                    "gross_edge_bps": 140.0,
                    "cost_bps": 46.0,
                    "net_edge_bps": 94.0,
                    "min_edge_bps": 48.5,
                    "atr_pct": 0.002,
                    "edge_context": {
                        "expected_move_bps": 140.0,
                        "total_cost_bps": 46.0,
                        "net_edge_bps": 94.0,
                        "adaptive_min_edge_bps": 48.5,
                        "spread_bps": 1.0,
                    },
                },
                "runtime_events": [{"event": "buy_accepted", "symbol": "XXBTZEUR", "side": "buy"}],
            },
            {
                "id": "inst-eth",
                "name": "Grid ETH",
                "symbol": "XETHZEUR",
                "capital": 500.0,
                "profit": 3.0,
                "profit_pct": 0.6,
                "max_drawdown": 0.01,
                "open_positions": 0,
                "warmup": {"active": False},
                "blocked_reasons": [],
                "last_signal": {"symbol": "XETHZEUR", "side": "buy", "price": 1900},
                "last_decision": {
                    "symbol": "XETHZEUR",
                    "gross_edge_bps": 90.0,
                    "cost_bps": 30.0,
                    "net_edge_bps": 60.0,
                    "min_edge_bps": 35.0,
                    "atr_pct": 0.0018,
                    "edge_context": {
                        "expected_move_bps": 90.0,
                        "total_cost_bps": 30.0,
                        "net_edge_bps": 60.0,
                        "adaptive_min_edge_bps": 35.0,
                        "spread_bps": 1.4,
                    },
                },
                "runtime_events": [{"event": "buy_rejected", "symbol": "XETHZEUR", "side": "buy"}],
            },
        ]


def test_colony_manager_builds_paper_children_without_live_promotion():
    manager = ColonyManager(
        ColonyConfig(
            target_live_capital_eur=500.0,
            max_paper_children=4,
            min_child_capital_eur=75.0,
            auto_live_promotion=False,
            max_auto_live_capital_eur=0.0,
        )
    )
    snapshot = manager.build_snapshot(
        opportunities=[
            {"symbol": "XXBTZEUR", "score": 85.0, "gross_edge_bps": 140.0, "net_edge_bps": 94.0, "atr_bps": 20.0, "spread_bps": 1.0},
            {"symbol": "XETHZEUR", "score": 72.0, "gross_edge_bps": 90.0, "net_edge_bps": 60.0, "atr_bps": 18.0, "spread_bps": 1.4},
        ],
        instances=[],
        capital={"total_capital": 1000.0},
        paper_mode=True,
    )

    assert snapshot["mode"] == "paper"
    assert snapshot["execution"]["live_activation_blocked"] is True
    assert snapshot["capital_model"]["target_live_capital_eur"] == 500.0
    assert snapshot["children"]
    assert all(child["paper_only"] for child in snapshot["children"])
    assert all(child["behavior"] != "explorer" for child in snapshot["children"])


def test_colony_endpoint_returns_control_plane(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("COLONY_TARGET_LIVE_CAPITAL_EUR", "500")
    dashboard.app.state.orchestrator = _Orchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/colony", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["implementation_stage"] == "paper_control_plane"
    assert body["paper_mode"] is True
    assert body["execution"]["auto_live_promotion"] is False
    assert body["children"]
