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
