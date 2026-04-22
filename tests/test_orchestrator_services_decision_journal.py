from autobot.v2.orchestrator_services import DecisionJournalService


class _Journal:
    def __init__(self):
        self.calls = []

    def log(self, **kwargs):
        self.calls.append(kwargs)


def test_decision_journal_service_logs_when_enabled(monkeypatch):
    monkeypatch.setenv("DECISION_JOURNAL_SESSION_ID", "session-1")
    journal = _Journal()
    service = DecisionJournalService(journal, enabled=True)

    service.major_decision(
        decision_type="activation_decision",
        source="test",
        symbols=["BTC/USD"],
        reasons=["promote"],
        context={"k": 1},
    )

    assert len(journal.calls) == 1
    assert journal.calls[0]["session_id"] == "session-1"
    assert service.fingerprint({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'


def test_decision_journal_service_skips_when_disabled():
    journal = _Journal()
    service = DecisionJournalService(journal, enabled=False)
    service.rejected_opportunity(reason="blocked", source="test", symbol="ETH/USD")
    assert journal.calls == []
