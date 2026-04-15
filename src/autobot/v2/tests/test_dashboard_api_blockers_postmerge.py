from fastapi.testclient import TestClient

from autobot.v2.api import dashboard


class _AsyncStopOrchestrator:
    def __init__(self):
        self._running = True

    async def stop(self):
        self._running = False

    def get_status(self):
        return {
            "running": self._running,
            "instance_count": 1,
            "websocket_connected": True,
            "start_time": None,
            "instances": [{"id": "i1", "name": "inst", "capital": 1000.0, "running": self._running}],
        }


class _StatusFallbackOrchestrator:
    def get_status(self):
        # Async-orchestrator-like payload without per-instance profit field
        return {
            "running": True,
            "instance_count": 2,
            "websocket_connected": True,
            "start_time": None,
            "instances": [
                {"id": "i1", "name": "a", "capital": 1000.0, "running": True},
                {"id": "i2", "name": "b", "capital": 500.0, "running": True},
            ],
        }

    def get_instances_snapshot(self):
        return [
            {
                "id": "i1",
                "name": "a",
                "capital": 1000.0,
                "profit": 12.5,
                "status": "running",
                "strategy": "grid",
                "open_positions": 1,
            },
            {
                "id": "i2",
                "name": "b",
                "capital": 500.0,
                "profit": -2.0,
                "status": "running",
                "strategy": "grid",
                "open_positions": 0,
            },
        ]



def test_emergency_stop_awaits_async_orchestrator_stop(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    dashboard.app.state.orchestrator = _AsyncStopOrchestrator()
    client = TestClient(dashboard.app)

    r = client.post(
        "/api/emergency-stop",
        headers={"Authorization": "Bearer tok"},
        json={"confirmation": "CONFIRM_STOP"},
    )

    assert r.status_code == 200
    assert r.json()["status"] == "stopped"
    assert dashboard.app.state.orchestrator.get_status()["running"] is False



def test_status_total_profit_uses_snapshot_when_status_instances_have_no_profit(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    dashboard.app.state.orchestrator = _StatusFallbackOrchestrator()
    client = TestClient(dashboard.app)

    r = client.get("/api/status", headers={"Authorization": "Bearer tok"})

    assert r.status_code == 200
    body = r.json()
    assert body["total_capital"] == 1500.0
    assert body["total_profit"] == 10.5
