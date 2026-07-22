from __future__ import annotations

import asyncio
import sqlite3

import pytest

from autobot.v2.global_kill_switch import GlobalKillSwitchStore, GlobalKillSwitchStoreError
from autobot.v2.kill_switch import KillSwitch


pytestmark = pytest.mark.unit


def test_locked_global_store_fails_closed_after_bounded_retries(monkeypatch, tmp_path):
    store = GlobalKillSwitchStore(
        str(tmp_path / "global_kill.db"),
        sqlite_timeout_seconds=0.001,
        retry_attempts=3,
        retry_delay_seconds=0.0,
        sleeper=lambda _: None,
    )
    attempts = {"count": 0}

    def locked_read():
        attempts["count"] += 1
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, "_read_persisted_state", locked_read)

    state = store.get()

    assert attempts["count"] == 3
    assert state.tripped is True
    assert state.recovery_required is True
    assert state.storage_healthy is False
    assert state.reason_code == "kill_switch_store_unavailable"
    assert KillSwitch(global_store=store).is_globally_tripped() is True


def test_persisted_acknowledgement_failure_keeps_local_kill_switch_tripped(monkeypatch, tmp_path):
    async def run() -> None:
        store = GlobalKillSwitchStore(str(tmp_path / "global_kill.db"))
        switch = KillSwitch(global_store=store)
        await switch.trigger("api_failures", "fixture")
        original = store._run_sqlite

        def fail_acknowledgement(operation, *, operation_name=""):
            if operation_name == "acknowledge":
                raise GlobalKillSwitchStoreError("global kill-switch acknowledge operation failed: OperationalError")
            return original(operation, operation_name=operation_name)

        monkeypatch.setattr(store, "_run_sqlite", fail_acknowledgement)

        with pytest.raises(GlobalKillSwitchStoreError, match="acknowledge"):
            switch.acknowledge_recovery("operator")

        assert switch.tripped is True

    asyncio.run(run())


def test_failed_global_persistence_does_not_cancel_local_halt(monkeypatch, tmp_path):
    async def run() -> None:
        store = GlobalKillSwitchStore(str(tmp_path / "global_kill.db"))
        switch = KillSwitch(global_store=store)

        def fail_trip(operation, *, operation_name=""):
            if operation_name == "trip":
                raise GlobalKillSwitchStoreError("global kill-switch trip operation failed: OperationalError")
            return operation()

        monkeypatch.setattr(store, "_run_sqlite", fail_trip)
        await switch.trigger("api_failures", "fixture")

        assert switch.tripped is True
        assert switch.last_event is not None
        assert switch.last_event.rule == "api_failures"

    asyncio.run(run())


def test_invalid_retry_configuration_is_rejected_before_opening_a_database(tmp_path):
    with pytest.raises(ValueError, match="retry configuration"):
        GlobalKillSwitchStore(str(tmp_path / "global_kill.db"), retry_attempts=0)
