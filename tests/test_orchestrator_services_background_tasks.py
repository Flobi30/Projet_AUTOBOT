import asyncio

import pytest

from autobot.v2.orchestrator_services import BackgroundTasksService


pytestmark = pytest.mark.integration

@pytest.mark.asyncio
async def test_background_tasks_service_start_and_stop():
    service = BackgroundTasksService()
    ticked = asyncio.Event()

    async def _loop():
        while True:
            ticked.set()
            await asyncio.sleep(0.01)

    service.start({"worker": _loop})
    await asyncio.wait_for(ticked.wait(), timeout=1.0)

    assert "worker" in service.tasks
    assert not service.tasks["worker"].done()

    await service.stop(["worker"])
    assert "worker" not in service.tasks
