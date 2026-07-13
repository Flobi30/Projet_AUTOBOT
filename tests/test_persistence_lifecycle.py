from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from autobot.v2.persistence import close_persistence, get_persistence


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_close_persistence_releases_and_resets_the_process_singleton(tmp_path):
    await close_persistence()
    persistence = get_persistence(str(tmp_path / "state.db"))
    assert await persistence.append_audit_event(
        event_id="persistence-lifecycle-1",
        event_type="TEST",
        instance_id="test",
        config_hash="test",
        risk_snapshot={},
    ) is True

    await close_persistence()

    assert persistence.audit._conn is None
    assert get_persistence(str(tmp_path / "replacement.db")) is not persistence
    await close_persistence()


@pytest.mark.asyncio
async def test_orchestrator_shutdown_releases_persistence_after_component_failure(monkeypatch):
    """A failed shutdown component must not strand SQLite worker threads."""
    from autobot.v2 import orchestrator_async

    close_mock = AsyncMock()
    monkeypatch.setattr(orchestrator_async, "close_persistence", close_mock)

    class FailingBackgroundTasks:
        async def stop(self):
            raise RuntimeError("simulated shutdown failure")

    orchestrator = SimpleNamespace(
        running=True,
        _main_task=None,
        background_tasks=FailingBackgroundTasks(),
    )

    with pytest.raises(RuntimeError, match="simulated shutdown failure"):
        await orchestrator_async.OrchestratorAsync.stop(orchestrator)

    assert orchestrator.running is False
    close_mock.assert_awaited_once()
