import pytest
from fastapi.testclient import TestClient

from autobot.v2.api import dashboard
from autobot.v2.strategy_governance import StrategyGovernanceConfig, StrategyGovernanceEngine


pytestmark = pytest.mark.unit


def _engine() -> StrategyGovernanceEngine:
    return StrategyGovernanceEngine(
        StrategyGovernanceConfig(
            enabled=True,
            apply_to_execution=True,
            block_on_no_trade=True,
            block_on_divergence=True,
            allow_non_grid_shadow_mirror=True,
            candidate_score_min=70.0,
        )
    )


def _router_route(engine: str, *, action: str, score: float = 82.0, support: str = "paper_official_candidate"):
    return {
        "symbol": "TRXEUR",
        "selected_engine": engine,
        "selected_variant": f"{engine}_variant",
        "router_score": score,
        "recommended_action": action,
        "reason": "test_reason",
        "paper_execution_policy": {
            "support": support,
            "reason": "test_support",
        },
    }


def test_strategy_governance_blocks_router_no_trade():
    snapshot = _engine().build_snapshot(
        router_snapshot={"routes": [_router_route("no_trade", action="no_trade", score=48.0, support="abstain")]},
        reconciliation_snapshot={"symbols": []},
        paper_mode=True,
        instance_state_by_symbol={"TRXEUR": {"open_positions": 0}},
    )

    row = snapshot["by_symbol"]["TRXEUR"]
    assert row["governance_status"] == "blocked"
    assert row["block_new_entries"] is True
    assert row["official_execution_engine"] == "none"


def test_strategy_governance_keeps_non_grid_shadow_candidate_observe_only():
    snapshot = _engine().build_snapshot(
        router_snapshot={"routes": [_router_route("trend_momentum", action="shadow_candidate_review")]},
        reconciliation_snapshot={"symbols": [{"symbol": "TRXEUR", "verdict": "aligned_positive", "recommended_action": "continue"}]},
        paper_mode=True,
        instance_state_by_symbol={"TRXEUR": {"open_positions": 0}},
    )

    row = snapshot["by_symbol"]["TRXEUR"]
    assert row["governance_status"] == "review"
    assert row["execution_mode"] == "observe_only"
    assert row["allow_shadow_signal_mirror"] is False
    assert row["allow_grid_entries"] is False
    assert row["block_new_entries"] is True


def test_strategy_governance_does_not_mirror_non_grid_candidate_with_open_positions():
    snapshot = _engine().build_snapshot(
        router_snapshot={"routes": [_router_route("mean_reversion", action="shadow_candidate_review")]},
        reconciliation_snapshot={"symbols": [{"symbol": "TRXEUR", "verdict": "aligned_positive", "recommended_action": "continue"}]},
        paper_mode=True,
        instance_state_by_symbol={"TRXEUR": {"open_positions": 2}},
    )

    row = snapshot["by_symbol"]["TRXEUR"]
    assert row["governance_status"] == "review"
    assert row["execution_mode"] == "observe_only"
    assert row["block_new_entries"] is True


class _GovernanceOrchestrator:
    paper_mode = True

    def get_status(self):
        return {
            "running": True,
            "instance_count": 1,
            "websocket_connected": True,
            "capital": {"paper_mode": True},
        }

    def get_instances_snapshot(self):
        return [{"id": "inst-trx", "symbol": "TRXEUR", "capital": 800.0}]

    async def _build_strategy_governance_snapshot(self, *, force: bool = False):
        return {
            "summary": {
                "symbols": 1,
                "eligible_symbols": 1,
                "blocked_symbols": 0,
                "mirror_symbols": 1,
                "pending_flat_symbols": 0,
            },
            "symbols": [
                {
                    "symbol": "TRXEUR",
                    "selected_engine": "trend_momentum",
                    "selected_variant": "trend_breakout",
                    "governance_status": "eligible",
                    "decision": "mirror_non_grid_candidate",
                    "execution_mode": "shadow_signal_mirror",
                    "official_execution_engine": "trend_momentum",
                    "allow_grid_entries": False,
                    "allow_shadow_signal_mirror": True,
                    "block_new_entries": True,
                    "reason": "non_grid_shadow_candidate_eligible_for_paper_mirror",
                    "reasons": ["non_grid_shadow_candidate_eligible_for_paper_mirror"],
                }
            ],
            "by_symbol": {
                "TRXEUR": {
                    "symbol": "TRXEUR",
                    "selected_engine": "trend_momentum",
                    "governance_status": "eligible",
                }
            },
            "message": "test",
        }


def test_strategy_governance_endpoint_returns_runtime_snapshot(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    dashboard.app.state.orchestrator = _GovernanceOrchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/strategy-governance", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["mirror_symbols"] == 1
    assert body["runtime"]["instance_count"] == 1
