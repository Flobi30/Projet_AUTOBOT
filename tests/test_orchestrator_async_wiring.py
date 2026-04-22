from autobot.v2.orchestrator_async import OrchestratorAsync
from autobot.v2.orchestrator_services import DecisionJournalService


class _Journal:
    def __init__(self):
        self.calls = []

    def log(self, **kwargs):
        self.calls.append(kwargs)


def test_orchestrator_journal_methods_are_wired_to_service():
    orchestrator = OrchestratorAsync.__new__(OrchestratorAsync)
    journal = _Journal()
    orchestrator.decision_journal_service = DecisionJournalService(journal=journal, enabled=True)

    orchestrator._journal_major_decision(
        decision_type="ranking_decision",
        source="pair_ranking_engine",
        symbols=["BTC/USD"],
        reasons=["refresh"],
        context={"rank": 1},
    )
    orchestrator._journal_rejected_opportunity(
        reason="symbol_not_selected",
        source="instance_activation_policy",
        symbol="ETH/USD",
        context={"tier": 1},
    )

    assert len(journal.calls) == 2
    assert orchestrator._fingerprint({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'
