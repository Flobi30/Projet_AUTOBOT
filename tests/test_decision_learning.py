from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from autobot.v2.api import dashboard
from autobot.v2.decision_learning import DecisionLearningConfig, DecisionLearningEngine
from autobot.v2.persistence import StatePersistence


pytestmark = pytest.mark.integration


def _ts(base: datetime, minutes: int) -> str:
    return (base + timedelta(minutes=minutes)).isoformat()


@pytest.mark.asyncio
async def test_decision_learning_labels_rejected_buy_as_missed_profit(tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    decision_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    created_at = decision_at.isoformat()
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
        await persistence.append_market_price_samples([
            {
                "symbol": "TRXEUR",
                "price": 100.2,
                "observed_at": _ts(decision_at, 5),
                "bucket_start": _ts(decision_at, 5),
                "source": "test",
            },
            {
                "symbol": "TRXEUR",
                "price": 100.5,
                "observed_at": _ts(decision_at, 10),
                "bucket_start": _ts(decision_at, 10),
                "source": "test",
            },
        ])

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
            instances=[],
        )

        assert snapshot["refreshed"] == 1
        rows = await persistence.get_signal_outcomes(limit=5, symbol="TRXEUR")
        assert len(rows) == 1
        assert rows[0]["outcome_label"] == "missed_profit"
        assert rows[0]["net_return_bps"] == pytest.approx(40.0)
        assert rows[0]["source"] == "decision_learning_triple_barrier"
        assert rows[0]["payload"]["barrier_touched"] == "take_profit"
    finally:
        await persistence.close()


@pytest.mark.asyncio
async def test_decision_learning_labels_rejected_buy_as_saved_loss(tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    decision_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    created_at = decision_at.isoformat()
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
        await persistence.append_market_price_samples([
            {
                "symbol": "ETHEUR",
                "price": 99.8,
                "observed_at": _ts(decision_at, 5),
                "bucket_start": _ts(decision_at, 5),
                "source": "test",
            },
            {
                "symbol": "ETHEUR",
                "price": 99.5,
                "observed_at": _ts(decision_at, 10),
                "bucket_start": _ts(decision_at, 10),
                "source": "test",
            },
        ])

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
            instances=[],
        )

        assert snapshot["refreshed"] == 1
        rows = await persistence.get_signal_outcomes(limit=5, symbol="ETHEUR")
        assert rows[0]["outcome_label"] == "saved_loss"
        assert rows[0]["net_return_bps"] == pytest.approx(-55.0)
        assert rows[0]["payload"]["barrier_touched"] == "stop_loss"
    finally:
        await persistence.close()


@pytest.mark.asyncio
async def test_decision_learning_relabels_legacy_proxy_with_linked_signal_price(tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    decision_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    created_at = decision_at.isoformat()
    try:
        await persistence.append_decision_ledger_event(
            event_id="dlg_signal_linked",
            signal_id="sig_linked",
            instance_id="inst_1",
            symbol="TRXEUR",
            strategy="grid",
            engine="grid",
            event_type="signal",
            event_status="signal_received",
            reason="Grid buy",
            source="strategy_signal",
            payload={"side": "buy", "price": 100.0},
            created_at=_ts(decision_at, -1),
        )
        await persistence.append_decision_ledger_event(
            event_id="dlg_decision_linked",
            decision_id="dec_linked",
            signal_id="sig_linked",
            instance_id="inst_1",
            symbol="TRXEUR",
            strategy="grid",
            engine="grid",
            event_type="decision",
            event_status="buy_rejected",
            reason="opportunity_selection",
            source="signal_handler_runtime",
            payload={"side": "buy", "cost_bps": 10.0},
            created_at=created_at,
        )
        candidates = await persistence.get_decision_outcome_candidates(horizon_minutes=15, limit=5)
        assert len(candidates) == 1
        await persistence.upsert_signal_outcome(
            outcome_id="legacy_proxy",
            decision_ledger_id=candidates[0]["id"],
            decision_event_id="dlg_decision_linked",
            decision_id="dec_linked",
            signal_id="sig_linked",
            instance_id="inst_1",
            symbol="TRXEUR",
            strategy="grid",
            engine="grid",
            side="buy",
            original_status="buy_rejected",
            rejection_reason="opportunity_selection",
            reference_price=100.0,
            evaluation_price=100.1,
            gross_return_bps=10.0,
            estimated_cost_bps=10.0,
            net_return_bps=0.0,
            horizon_minutes=15,
            outcome_label="flat",
            source="decision_learning_current_price_proxy",
            payload={"method": "point_in_time_proxy"},
            decision_created_at=created_at,
            evaluated_at=_ts(decision_at, 16),
            created_at=_ts(decision_at, 16),
        )
        await persistence.append_market_price_samples([
            {
                "symbol": "TRXEUR",
                "price": 100.2,
                "observed_at": _ts(decision_at, 5),
                "bucket_start": _ts(decision_at, 5),
                "source": "test",
            },
            {
                "symbol": "TRXEUR",
                "price": 100.5,
                "observed_at": _ts(decision_at, 10),
                "bucket_start": _ts(decision_at, 10),
                "source": "test",
            },
        ])

        engine = DecisionLearningEngine(
            DecisionLearningConfig(
                enabled=True,
                horizons_minutes=(15,),
                max_candidates_per_horizon=20,
                recent_limit=10,
                take_profit_bps=35.0,
                stop_loss_bps=35.0,
                allow_proxy_fallback=False,
            )
        )
        snapshot = await engine.refresh(persistence=persistence, instances=[])

        assert snapshot["refreshed"] == 1
        assert snapshot["legacy_proxy_outcomes_ignored"] == 0
        assert snapshot["summary"]["by_source"]["decision_learning_triple_barrier"] == 1
        rows = await persistence.get_signal_outcomes(limit=5, symbol="TRXEUR")
        assert len(rows) == 1
        assert rows[0]["source"] == "decision_learning_triple_barrier"
        assert rows[0]["outcome_label"] == "missed_profit"
        assert rows[0]["payload"]["barrier_touched"] == "take_profit"
    finally:
        await persistence.close()


@pytest.mark.asyncio
async def test_decision_learning_summary_ignores_legacy_proxy_when_strict(tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    decision_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    try:
        await persistence.append_decision_ledger_event(
            event_id="dlg_proxy_only",
            decision_id="dec_proxy_only",
            signal_id="sig_proxy_only",
            instance_id="inst_1",
            symbol="TRXEUR",
            strategy="grid",
            engine="grid",
            event_type="decision",
            event_status="buy_rejected",
            reason="opportunity_selection",
            source="signal_handler_runtime",
            payload={"side": "buy", "signal_price": 100.0},
            created_at=decision_at.isoformat(),
        )
        candidates = await persistence.get_decision_outcome_candidates(horizon_minutes=15, limit=5)
        await persistence.upsert_signal_outcome(
            outcome_id="proxy_only",
            decision_ledger_id=candidates[0]["id"],
            decision_event_id="dlg_proxy_only",
            decision_id="dec_proxy_only",
            signal_id="sig_proxy_only",
            instance_id="inst_1",
            symbol="TRXEUR",
            strategy="grid",
            engine="grid",
            side="buy",
            original_status="buy_rejected",
            rejection_reason="opportunity_selection",
            reference_price=100.0,
            evaluation_price=101.0,
            gross_return_bps=100.0,
            estimated_cost_bps=10.0,
            net_return_bps=90.0,
            horizon_minutes=15,
            outcome_label="missed_profit",
            source="decision_learning_current_price_proxy",
            payload={"method": "point_in_time_proxy"},
            decision_created_at=decision_at.isoformat(),
            evaluated_at=_ts(decision_at, 16),
            created_at=_ts(decision_at, 16),
        )

        engine = DecisionLearningEngine(DecisionLearningConfig(allow_proxy_fallback=False))
        snapshot = await engine.snapshot(persistence=persistence)

        assert snapshot["summary"]["evaluated"] == 0
        assert snapshot["legacy_proxy_outcomes_ignored"] == 1
        assert snapshot["legacy_proxy_summary"]["evaluated"] == 1
    finally:
        await persistence.close()


class _LearningOrchestrator:
    paper_mode = True

    def __init__(self, persistence, decision_at: datetime):
        self.persistence = persistence
        self._decision_at = decision_at

    def get_status(self):
        return {
            "running": True,
            "instance_count": 1,
            "websocket_connected": True,
            "capital": {"paper_mode": True},
        }

    def get_instances_snapshot(self):
        return [{
            "symbol": "TRXEUR",
            "last_price": 100.5,
            "price_history_tail": [
                {"timestamp": _ts(self._decision_at, 5), "price": 100.2},
                {"timestamp": _ts(self._decision_at, 10), "price": 100.5},
            ],
        }]


@pytest.mark.asyncio
async def test_decision_learning_endpoint_returns_outcome_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("DECISION_LEARNING_HORIZONS_MIN", "15")
    persistence = StatePersistence(str(tmp_path / "state.db"))
    decision_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    created_at = decision_at.isoformat()
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

        dashboard.app.state.orchestrator = _LearningOrchestrator(persistence, decision_at)
        client = TestClient(dashboard.app)
        response = client.get("/api/decision-learning", headers={"Authorization": "Bearer tok"})

        assert response.status_code == 200
        body = response.json()
        assert body["safety"]["writes_orders"] is False
        assert body["refreshed"] == 1
        assert body["summary"]["by_label"]["missed_profit"] == 1
        assert body["summary"]["by_source"]["decision_learning_triple_barrier"] == 1
    finally:
        await persistence.close()
