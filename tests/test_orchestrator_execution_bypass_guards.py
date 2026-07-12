from types import SimpleNamespace

import pytest

from autobot.v2.orchestrator_async import OrchestratorAsync


pytestmark = pytest.mark.unit


def test_legacy_leverage_activation_fails_closed_before_reading_instance_state():
    orchestrator = object.__new__(OrchestratorAsync)
    orchestrator._legacy_leverage_activation_enabled = False
    instance = SimpleNamespace(
        get_current_capital=lambda: (_ for _ in ()).throw(AssertionError("must not inspect capital")),
    )

    assert orchestrator.check_leverage_activation(instance) is False


@pytest.mark.asyncio
async def test_legacy_pyramiding_fails_closed_before_reading_positions():
    orchestrator = object.__new__(OrchestratorAsync)
    orchestrator._legacy_position_add_enabled = False
    instance = SimpleNamespace(
        get_status=lambda: (_ for _ in ()).throw(AssertionError("must not inspect positions")),
    )

    assert await orchestrator._evaluate_add_position(instance) == 0
