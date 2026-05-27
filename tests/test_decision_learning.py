from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from autobot.v2.api import dashboard
from autobot.v2.decision_learning import DecisionLearningConfig, DecisionLearningEngine
from autobot.v2.persistence import StatePersistence


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_decision_learning_labels_rejected_buy_as_missed_profit(tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    created_at = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    try:
        await persistence.append_decision_ledger_event(
            event_id="dlg_reject_1",
            decision_id="dec_reject_1",
            signal_id="sig_reject_1",
            instance_id="inst_1",
            symbol="TRXEUR",
            strategy="grid",
            engine="grid",
            event_type="decision",
            event_status="buy_rejected",
            reason="cost_guard",
            source="signal_handler_runtime",
            payload={"side": "buy", "signal_price": 100.0, "cost_bps": 10.0},
            created_at=created_at,
        )

        engine = DecisionLearningEngine(
            DecisionLearningConfig(
                enabled=True,
                horizons_minutes=(15,),
                max_candidates_per_horizon=20,
                recent_limit=10,
                take_profit_bps=35.0,
                stop_loss_bps=35.0,
            )
        )
        snapshot = await engine.refresh(
            persistence=persistence,
            instances=[{"symbol": "TRXEUR", "last_price": 100.5}],
        )

        assert snapshot["refreshed"] == 1
        rows = await persistence.get_signal_outcomes(limit=5, symbol="TRXEUR")
        assert len(rows) == 1
        assert rows[0]["outcome_label"] == "missed_profit"
        assert rows[0]["net_return_bps"] == pytest.approx(40.0)
    finally:
        await persistence.close()


@pytest.mark.asyncio
async def test_decision_learning_labels_rejected_buy_as_saved_loss(tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    created_at = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    try:
        await persistence.append_decision_ledger_event(
            event_id="dlg_reject_2",
            decision_id="dec_reject_2",
            signal_id="sig_reject_2",
            instance_id="inst_1",
            symbol="ETHEUR",
            strategy="grid",
            engine="grid",
            event_type="decision",
            event_status="buy_rejected",
            reason="opportunity_selection",
            source="signal_handler_runtime",
            payload={"side": "buy", "signal_price": 100.0, "edge_context": {"total_cost_bps": 5.0}},
            created_at=created_at,
        )

        engine = DecisionLearningEngine(
            DecisionLearningConfig(
                enabled=True,
                horizons_minutes=(15,),
                max_candidates_per_horizon=20,
                recent_limit=10,
                take_profit_bps=35.0,
                stop_loss_bps=35.0,
            )
        )
        snapshot = await engine.refresh(
            persistence=persistence,
            instances=[{"symbol": "ETHEUR", "last_price": 99.5}],
        )

        assert snapshot["refreshed"] == 1
        rows = await persistence.get_signal_outcomes(limit=5, symbol="ETHEUR")
        assert rows[0]["outcome_label"] == "saved_loss"
        assert rows[0]["net_return_bps"] == pytest.approx(-55.0)
    finally:
        await persistence.close()


class _LearningOrchestrator:
    paper_mode = True

    def __init__(self, persistence):
        self.persistence = persistence

    def get_status(self):
        return {
            "running": True,
            "instance_count": 1,
            "websocket_connected": True,
            "capital": {"paper_mode": True},
        }

    def get_instances_snapshot(self):
        return [{"symbol": "TRXEUR", "last_price": 100.5}]


@pytest.mark.asyncio
async def test_decision_learning_endpoint_returns_outcome_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("DECISION_LEARNING_HORIZONS_MIN", "15")
    persistence = StatePersistence(str(tmp_path / "state.db"))
    created_at = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    try:
        await persistence.append_decision_ledger_event(
            event_id="dlg_endpoint",
            decision_id="dec_endpoint",
            signal_id="sig_endpoint",
            instance_id="inst_1",
            symbol="TRXEUR",
            strategy="grid",
            engine="grid",
            event_type="decision",
            event_status="buy_rejected",
            reason="cost_guard",
            source="signal_handler_runtime",
            payload={"side": "buy", "signal_price": 100.0, "cost_bps": 10.0},
            created_at=created_at,
        )

        dashboard.app.state.orchestrator = _LearningOrchestrator(persistence)
        client = TestClient(dashboard.app)
        response = client.get("/api/decision-learning", headers={"Authorization": "Bearer tok"})

        assert response.status_code == 200
        body = response.json()
        assert body["safety"]["writes_orders"] is False
        assert body["refreshed"] == 1
        assert body["summary"]["by_label"]["missed_profit"] == 1
    finally:
        await persistence.close()
