import sqlite3

import pytest

from autobot.v2.governance_observability import GovernanceDecisionObserver
from autobot.v2.persistence import StatePersistence


pytestmark = pytest.mark.unit


def _snapshot(*, engine="no_trade", decision="abstain", status="blocked", block=True):
    return {
        "symbols": [
            {
                "symbol": "TRXEUR",
                "selected_engine": engine,
                "selected_variant": "abstain" if engine == "no_trade" else "grid_balanced",
                "decision": decision,
                "governance_status": status,
                "execution_mode": "observe_only",
                "block_new_entries": block,
                "official_execution_engine": "none",
                "reason": "router_selected_no_trade" if engine == "no_trade" else "official_underperforming",
                "router_score": 60.0,
            }
        ]
    }


def test_no_trade_is_bounded_and_live_remains_false():
    observer = GovernanceDecisionObserver(reminder_interval_seconds=300)
    instances = {"TRXEUR": {"id": "inst-trx", "strategy": "grid"}}

    first = observer.collect(_snapshot(), instance_by_symbol=instances, now=100.0)
    duplicate = observer.collect(_snapshot(), instance_by_symbol=instances, now=200.0)
    reminder = observer.collect(_snapshot(), instance_by_symbol=instances, now=401.0)

    assert len(first) == 1
    assert first[0].event_type == "no_trade"
    assert first[0].event_status == "abstain"
    assert first[0].payload["live_promotion_allowed"] is False
    assert duplicate == ()
    assert len(reminder) == 1


def test_governance_block_is_classified_without_execution():
    observer = GovernanceDecisionObserver()
    events = observer.collect(
        _snapshot(engine="dynamic_grid", decision="pause_grid_review_divergence"),
        instance_by_symbol={"TRXEUR": {"id": "inst-trx", "strategy": "grid"}},
        now=10.0,
    )

    assert len(events) == 1
    assert events[0].event_type == "governance_block"
    assert events[0].payload["block_new_entries"] is True
    assert "order" not in events[0].payload


@pytest.mark.asyncio
async def test_no_trade_persists_without_creating_order(tmp_path):
    db_path = tmp_path / "state.db"
    persistence = StatePersistence(str(db_path))
    observer = GovernanceDecisionObserver()
    try:
        event = observer.collect(
            _snapshot(),
            instance_by_symbol={"TRXEUR": {"id": "inst-trx", "strategy": "grid"}},
            now=10.0,
        )[0]
        assert await persistence.append_decision_ledger_event(**observer.event_kwargs(event)) is True
        rows = await persistence.get_decision_ledger_events(limit=5)
        assert rows[0]["event_type"] == "no_trade"
        assert rows[0]["reason"] == "router_selected_no_trade"

        connection = sqlite3.connect(db_path)
        try:
            assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        await persistence.close()
