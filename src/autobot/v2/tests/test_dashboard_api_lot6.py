from types import SimpleNamespace

from fastapi.testclient import TestClient

from autobot.v2.api import dashboard
import autobot.v2.config as config


class _DummyUniverse:
    def snapshot(self):
        return SimpleNamespace(
            supported=frozenset({"BTC/EUR", "ETH/EUR"}),
            eligible=frozenset({"BTC/EUR"}),
            ranked=("BTC/EUR",),
            websocket_active=frozenset({"BTC/EUR"}),
            actively_traded=frozenset({"BTC/EUR"}),
        )

    def get_scored_universe(self):
        return {"BTC/EUR": {"score": 77.0, "formula": "x"}}

    def get_ranked_universe(self):
        return ["BTC/EUR"]


class _PairScore:
    def __init__(self, symbol, score):
        self.symbol = symbol
        self.score = score
        self.explain = {"formula": "x", "base_composite": score}


class _DummyRanking:
    def get_ranked_pairs(self):
        return [_PairScore("BTC/EUR", 77.0)]


class _DummyOrchestrator:
    def __init__(self):
        self.universe_manager = _DummyUniverse()
        self.pair_ranking_engine = _DummyRanking()

    def get_status(self):
        return {
            "running": True,
            "instance_count": 1,
            "instances": [{"capital": 1000.0, "profit": 10.0}],
            "websocket_connected": True,
            "start_time": None,
            "scalability_guard": {"state": "ALLOW_SCALE_UP", "reasons": [], "signals": {}},
            "activation": {"action": "hold", "target_instances": 1, "target_tier": 1, "selected_symbols": ["BTC/EUR"], "reason": "stable"},
            "portfolio_allocator": {
                "enabled": True,
                "plan": {
                    "symbol_caps": {"BTC/EUR": 150.0},
                    "total_allocated": 150.0,
                    "reserve_cash": 200.0,
                    "risk_budget_remaining": 20.0,
                    "reasons": {},
                    "explain": {"max_cluster_abs": 350.0},
                },
            },
        }


def _client():
    dashboard.app.state.orchestrator = _DummyOrchestrator()
    return TestClient(dashboard.app)


def test_lot6_endpoints_schema_enabled(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_SCALABILITY_GUARD", True)
    monkeypatch.setattr(config, "ENABLE_INSTANCE_ACTIVATION_MANAGER", True)
    monkeypatch.setattr(config, "ENABLE_UNIVERSE_MANAGER", True)
    monkeypatch.setattr(config, "ENABLE_PAIR_RANKING_ENGINE", True)
    monkeypatch.setattr(config, "ENABLE_PORTFOLIO_ALLOCATOR", True)
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tkn")

    c = _client()
    headers = {"Authorization": "Bearer tkn"}

    scaling = c.get("/api/scaling/status", headers=headers)
    universe = c.get("/api/universe/status", headers=headers)
    opportunities = c.get("/api/opportunities/top?limit=5", headers=headers)
    allocation = c.get("/api/portfolio/allocation", headers=headers)

    assert scaling.status_code == 200
    assert universe.status_code == 200
    assert opportunities.status_code == 200
    assert allocation.status_code == 200

    assert scaling.json()["guard"]["state"] == "ALLOW_SCALE_UP"
    assert universe.json()["counts"]["supported"] == 2
    assert opportunities.json()["opportunities"][0]["symbol"] == "BTC/EUR"
    assert allocation.json()["allocation"]["reserve_cash"] == 200.0


def test_lot6_endpoints_disabled_message(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_PAIR_RANKING_ENGINE", False)
    monkeypatch.setattr(config, "ENABLE_PORTFOLIO_ALLOCATOR", False)
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tkn")

    c = _client()
    headers = {"Authorization": "Bearer tkn"}

    opportunities = c.get("/api/opportunities/top", headers=headers).json()
    allocation = c.get("/api/portfolio/allocation", headers=headers).json()

    assert opportunities["enabled"] is False
    assert opportunities["message"] == "Feature disabled by configuration"
    assert allocation["enabled"] is False
    assert allocation["message"] == "Feature disabled by configuration"
