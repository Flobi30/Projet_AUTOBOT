import pytest
from fastapi.testclient import TestClient

from autobot.v2.api import dashboard
from autobot.v2.persistence import StatePersistence


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_decision_ledger_roundtrip(tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    try:
        await persistence.append_decision_ledger_event(
            event_id="dlg_1",
            decision_id="dec_1",
            signal_id="sig_1",
            instance_id="inst_1",
            symbol="TRXEUR",
            strategy="grid",
            engine="trend_momentum",
            event_type="decision",
            event_status="buy_accepted",
            reason="all_guards_passed",
            source="signal_handler_runtime",
            payload={"foo": "bar", "side": "buy"},
        )

        rows = await persistence.get_decision_ledger_events(limit=5, symbol="TRXEUR")

        assert len(rows) == 1
        assert rows[0]["decision_id"] == "dec_1"
        assert rows[0]["engine"] == "trend_momentum"
        assert rows[0]["payload"]["foo"] == "bar"
    finally:
        await persistence.close()


class _LedgerOrchestrator:
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


@pytest.mark.asyncio
async def test_decision_ledger_endpoint_returns_rows(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    persistence = StatePersistence(str(tmp_path / "state.db"))
    try:
        await persistence.append_decision_ledger_event(
            event_id="dlg_2",
            decision_id="dec_2",
            signal_id="sig_2",
            instance_id="inst_2",
            symbol="ETHEUR",
            strategy="grid",
            engine="mean_reversion",
            event_type="order",
            event_status="order_filled",
            reason="execution_success",
            source="signal_handler_runtime",
            payload={"bar": "baz"},
        )

        dashboard.app.state.orchestrator = _LedgerOrchestrator(persistence)
        client = TestClient(dashboard.app)
        response = client.get("/api/decision-ledger", headers={"Authorization": "Bearer tok"})

        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["events"] >= 1
        assert body["rows"][0]["symbol"] == "ETHEUR"
    finally:
        await persistence.close()
