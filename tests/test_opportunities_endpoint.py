import pytest
from fastapi.testclient import TestClient

from autobot.v2.api import dashboard
from autobot.v2.opportunity_scoring import OpportunityConfig, OpportunityScorer


pytestmark = pytest.mark.integration


def _range_price_history(start: float = 100.0):
    return [{"timestamp": f"2026-04-28T00:{i:02d}:00+00:00", "price": start + (i % 6) * 0.02} for i in range(60)]


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
            },
        }

    def get_instances_snapshot(self):
        return [
            {
                "id": "inst-eth",
                "name": "Grid ETHEUR",
                "symbol": "ETHEUR",
                "capital": 500.0,
                "open_positions": 0,
                "warmup": {"active": False},
                "blocked_reasons": [],
                "last_signal": {
                    "timestamp": "2026-04-28T01:00:00+00:00",
                    "event": "signal_received",
                    "symbol": "ETHEUR",
                    "side": "buy",
                    "price": 1955.72,
                },
                "last_decision": {
                    "timestamp": "2026-04-28T01:00:01+00:00",
                    "event": "buy_accepted",
                    "reason": "all_guards_passed",
                    "symbol": "ETHEUR",
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
                "runtime_events": [
                    {"event": "signal_received", "symbol": "ETHEUR", "side": "buy"},
                    {"event": "buy_accepted", "symbol": "ETHEUR", "side": "buy"},
                ],
                "price_history_tail": _range_price_history(1955.0),
            },
            {
                "id": "inst-btc",
                "name": "Grid BTCEUR",
                "symbol": "BTCEUR",
                "capital": 500.0,
                "open_positions": 0,
                "warmup": {"active": True},
                "blocked_reasons": ["no_price"],
                "last_signal": None,
                "last_decision": None,
                "runtime_events": [],
                "price_history_tail": _range_price_history(66500.0),
            },
        ]


def test_opportunity_scorer_marks_high_edge_signal_tradable():
    scorer = OpportunityScorer(
        OpportunityConfig(
            min_score=60.0,
            min_gross_edge_bps=35.0,
            min_net_edge_bps=12.0,
            min_atr_bps=18.0,
            min_stability=0.40,
        )
    )

    result = scorer.score_signal(
        symbol="ETHEUR",
        edge_context={
            "expected_move_bps": 140.0,
            "total_cost_bps": 46.0,
            "net_edge_bps": 94.0,
            "adaptive_min_edge_bps": 48.5,
            "spread_bps": 1.0,
        },
        atr_pct=0.002,
        available_capital=500.0,
        recent_events=[
            {"event": "signal_received", "symbol": "ETHEUR", "side": "buy"},
            {"event": "buy_accepted", "symbol": "ETHEUR", "side": "buy"},
        ],
    )

    assert result.status == "tradable"
    assert result.score >= 60.0
    assert result.base_score == result.score
    assert result.regime_context["regime"] == "unknown"
    assert result.recommended_order_eur > 0.0


def test_paper_adaptive_atr_allows_high_net_edge_only_in_paper():
    scorer = OpportunityScorer(
        OpportunityConfig(
            min_score=60.0,
            min_gross_edge_bps=35.0,
            min_net_edge_bps=12.0,
            min_atr_bps=18.0,
            paper_relaxed_min_atr_bps=5.0,
            high_net_edge_bps=80.0,
            atr_mode="adaptive",
            min_stability=0.40,
        )
    )
    edge_context = {
        "expected_move_bps": 140.0,
        "total_cost_bps": 46.0,
        "net_edge_bps": 94.0,
        "adaptive_min_edge_bps": 48.5,
        "spread_bps": 1.0,
    }

    paper_result = scorer.score_signal(
        symbol="ETHEUR",
        edge_context=edge_context,
        atr_pct=0.0008,
        available_capital=500.0,
        paper_mode=True,
    )
    live_result = scorer.score_signal(
        symbol="ETHEUR",
        edge_context=edge_context,
        atr_pct=0.0008,
        available_capital=500.0,
        paper_mode=False,
    )

    assert "atr_below_minimum" not in paper_result.blockers
    assert "atr_below_minimum" in live_result.blockers


def test_opportunities_endpoint_returns_ranked_runtime_scores(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    dashboard.app.state.orchestrator = _Orchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/opportunities", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "paper"
    assert body["execution_gate"]["selection_applies_to_execution"] is True
    assert body["opportunities"][0]["symbol"] == "ETHEUR"
    assert body["opportunities"][0]["status"] == "tradable"
    assert "base_score" in body["opportunities"][0]
    assert "regime_context" in body["opportunities"][0]
    assert not any(str(blocker).startswith("regime_") for blocker in body["opportunities"][0]["blockers"])
    assert "BTCEUR" in {item["symbol"] for item in body["opportunities"]}


def test_regime_endpoint_returns_runtime_pairs(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    dashboard.app.state.orchestrator = _Orchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/regime", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "paper"
    assert body["config"]["enabled"] is True
    assert {item["symbol"] for item in body["symbols"]} == {"ETHEUR", "BTCEUR"}
    assert all("entropy_norm" in item for item in body["symbols"])
