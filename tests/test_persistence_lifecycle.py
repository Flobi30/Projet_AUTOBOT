from __future__ import annotations

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
