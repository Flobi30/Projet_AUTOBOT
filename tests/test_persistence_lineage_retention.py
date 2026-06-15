import pytest

from autobot.v2.persistence import StatePersistence


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_cleanup_orphaned_instances_retains_lifetime_lineage(tmp_path):
    persistence = StatePersistence(str(tmp_path / "state.db"))
    await persistence.initialize()
    await persistence.save_instance_state(
        instance_id="orphan-parent",
        status="stopped",
        current_capital=1000.0,
        allocated_capital=0.0,
        win_count=0,
        loss_count=0,
        initial_capital=1000.0,
    )
    await persistence.record_instance_lineage(
        parent_instance_id="orphan-parent",
        child_instance_id="orphan-child",
        root_instance_id="orphan-parent",
        generation=1,
        child_capital=400.0,
        parent_capital_after=600.0,
        status="stopped",
    )

    deleted = await persistence.cleanup_orphaned_instances(["active-instance"])
    lineage = await persistence.get_instance_lineage()
    split_count = await persistence.get_parent_instance_split_count("orphan-parent")
    await persistence.close()

    assert deleted == 1
    assert len(lineage) == 1
    assert lineage[0]["parent_instance_id"] == "orphan-parent"
    assert split_count == 1
