import pytest

from autobot.v2.orchestrator_async import OrchestratorAsync


pytestmark = pytest.mark.unit


def _orchestrator_stub(*, paper_mode: bool, disable_legacy: bool, allow_live_direct: bool):
    orchestrator = object.__new__(OrchestratorAsync)
    orchestrator.paper_mode = paper_mode
    orchestrator._strategy_governance_disable_legacy_ensemble = disable_legacy
    orchestrator._strategy_governance_allow_legacy_direct_entry_live = allow_live_direct
    return orchestrator


def test_legacy_ensemble_direct_entries_disabled_by_default():
    orchestrator = _orchestrator_stub(
        paper_mode=True,
        disable_legacy=True,
        allow_live_direct=False,
    )

    assert orchestrator._legacy_ensemble_entry_enabled() is False


def test_legacy_ensemble_direct_entries_stay_blocked_in_live_without_explicit_guard_override():
    orchestrator = _orchestrator_stub(
        paper_mode=False,
        disable_legacy=False,
        allow_live_direct=False,
    )

    assert orchestrator._legacy_ensemble_entry_enabled() is False


def test_legacy_ensemble_direct_entries_remain_quarantined_even_with_old_overrides():
    orchestrator = _orchestrator_stub(
        paper_mode=False,
        disable_legacy=False,
        allow_live_direct=True,
    )

    assert orchestrator._legacy_ensemble_entry_enabled() is False


@pytest.mark.asyncio
async def test_legacy_shadow_paper_candidate_bridge_is_retired_before_runtime_access():
    orchestrator = object.__new__(OrchestratorAsync)

    result = await orchestrator._maybe_execute_shadow_paper_candidate(object())

    assert result == {
        "handled": False,
        "reason": "legacy_shadow_paper_bridge_retired",
        "research_only": True,
        "paper_capital_allowed": False,
        "live_allowed": False,
    }
