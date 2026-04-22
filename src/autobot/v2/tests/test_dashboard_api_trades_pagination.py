import pytest

from fastapi.testclient import TestClient

from autobot.v2.api import dashboard


pytestmark = pytest.mark.unit


class _TradesPersistenceStub:
    def get_trades_paginated(self, limit: int, offset: int):
        assert limit == 5
        assert offset == 0
        return {
            "total": 10,
            "items": [
                {"id": "t1", "pair": "BTC/EUR"},
                {"id": "t2", "pair": "ETH/EUR"},
            ],
        }


class _OrchestratorWithPersistence:
    def __init__(self):
        self.persistence = _TradesPersistenceStub()


class _OrchestratorWithoutPersistence:
    persistence = None

    def get_instances_snapshot(self):
        return [
            {
                "id": "inst-1",
                "name": "Instance 1",
                "strategy": "grid",
                "trades_history": [
                    {"id": "a", "timestamp": "2025-01-01T10:00:00+00:00", "pair": "BTC/EUR"},
                    {"id": "b", "timestamp": "2025-01-01T12:00:00+00:00", "pair": "ETH/EUR"},
                ],
            },
            {
                "id": "inst-2",
                "name": "Instance 2",
                "strategy": "trend",
                "trades_history": [
                    {"id": "c", "timestamp": "2025-01-01T11:00:00+00:00", "pair": "SOL/EUR"},
                    {"id": "d", "timestamp": "2025-01-01T13:00:00+00:00", "pair": "XRP/EUR"},
                ],
            },
        ]


def test_trades_pagination_fields_are_consistent(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    dashboard.app.state.orchestrator = _OrchestratorWithPersistence()
    client = TestClient(dashboard.app)

    response = client.get("/api/trades?limit=5&offset=0", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    pagination = response.json()["pagination"]
    assert pagination == {
        "limit": 5,
        "offset": 0,
        "returned": 2,
        "total": 10,
        "has_more": True,
        "next_offset": 2,
    }


def test_trades_fallback_uses_bounded_top_window(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    dashboard.app.state.orchestrator = _OrchestratorWithoutPersistence()
    client = TestClient(dashboard.app)

    response = client.get("/api/trades?limit=2&offset=1", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 4
    assert [trade["id"] for trade in payload["trades"]] == ["b", "c"]
    assert payload["pagination"] == {
        "limit": 2,
        "offset": 1,
        "returned": 2,
        "total": 4,
        "has_more": True,
        "next_offset": 3,
    }
