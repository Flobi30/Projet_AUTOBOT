from fastapi.testclient import TestClient

from autobot.v2.api import dashboard


class _LegacyOrchestrator:
    def get_status(self):
        return {
            "running": True,
            "instance_count": 1,
            "websocket_connected": True,
            "start_time": None,
            "instances": [{"capital": 1000.0, "profit": 10.0}],
        }

    def get_instances_snapshot(self):
        return [
            {
                "id": "i1",
                "name": "inst-1",
                "capital": 1000.0,
                "profit": 10.0,
                "status": "running",
                "strategy": "grid",
                "open_positions": 1,
            }
        ]

    def get_instance_positions_snapshot(self, instance_id: str):
        if instance_id != "i1":
            return None
        return [
            {
                "pair": "BTC/EUR",
                "side": "LONG",
                "size": "0.01",
                "entry_price": 60000.0,
                "current_price": 61000.0,
                "pnl": 10.0,
                "pnl_percent": 1.6,
            }
        ]


def test_legacy_dashboard_routes_still_work(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    dashboard.app.state.orchestrator = _LegacyOrchestrator()
    client = TestClient(dashboard.app)
    headers = {"Authorization": "Bearer tok"}

    s = client.get("/api/status", headers=headers)
    i = client.get("/api/instances", headers=headers)
    p = client.get("/api/instances/i1/positions", headers=headers)

    assert s.status_code == 200
    assert i.status_code == 200
    assert p.status_code == 200
    assert s.json()["instance_count"] == 1
    assert i.json()[0]["id"] == "i1"
    assert p.json()[0]["pair"] == "BTC/EUR"
