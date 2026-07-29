from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from autobot.v2.persistence import close_persistence, get_persistence
from autobot.v2.persistence import StatePersistence


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


@pytest.mark.asyncio
async def test_persistence_close_attempts_every_repository_before_reporting_a_failure(tmp_path):
    """A close failure must not strand sibling aiosqlite workers."""

    persistence = StatePersistence(str(tmp_path / "state.db"))
    closed: list[str] = []

    class CloseProbe:
        def __init__(self, name: str, *, fails: bool = False):
            self.name = name
            self.fails = fails

        async def close(self) -> None:
            closed.append(self.name)
            if self.fails:
                raise OSError(f"simulated close failure: {self.name}")

    persistence.orders._conn = CloseProbe("orders")
    persistence.audit._conn = CloseProbe("audit", fails=True)
    persistence.positions._conn = CloseProbe("positions")
    persistence.instance_state._conn = CloseProbe("instance_state")

    with pytest.raises(RuntimeError, match="audit:OSError"):
        await persistence.close()

    assert set(closed) == {"orders", "audit", "positions", "instance_state"}
    assert persistence.orders._conn is None
    assert persistence.audit._conn is None
    assert persistence.positions._conn is None
    assert persistence.instance_state._conn is None


@pytest.mark.asyncio
async def test_repository_close_times_out_and_detaches_a_stalled_connection(monkeypatch, tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    monkeypatch.setenv("SQLITE_CLOSE_TIMEOUT_SECONDS", "1")
    never_finishes = asyncio.Event()

    class StalledClose:
        async def close(self) -> None:
            await never_finishes.wait()

    persistence.orders._conn = StalledClose()

    with pytest.raises(RuntimeError, match="sqlite_repository_close_timed_out"):
        await persistence.orders.close()

    assert persistence.orders._conn is None
