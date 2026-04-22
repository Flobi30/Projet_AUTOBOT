import pytest

from autobot.v2.diagnostic_manager import DiagnosticManager


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_run_full_check_overall_is_critical_when_any_check_is_error(monkeypatch):
    diag = DiagnosticManager()

    async def docker_error():
        return {"status": "error", "error": "Docker down"}

    monkeypatch.setattr(diag, "_check_docker", docker_error)
    monkeypatch.setattr(diag, "_check_system", lambda: {"status": "ok"})

    async def network_ok():
        return {"status": "ok"}

    async def kraken_ok():
        return {"status": "ok"}

    monkeypatch.setattr(diag, "_check_network", network_ok)
    monkeypatch.setattr(diag, "_check_kraken", kraken_ok)
    monkeypatch.setattr(diag, "_check_database", lambda: {"status": "ok"})
    monkeypatch.setattr(diag, "_check_bot", lambda: {"status": "ok"})

    status = await diag.run_full_check()

    assert status.overall == "critical"


@pytest.mark.asyncio
async def test_run_full_check_overall_is_critical_when_any_check_is_critical(monkeypatch):
    diag = DiagnosticManager()

    async def docker_ok():
        return {"status": "ok"}

    monkeypatch.setattr(diag, "_check_docker", docker_ok)
    monkeypatch.setattr(diag, "_check_system", lambda: {"status": "critical", "warning": "RAM critique"})

    async def network_ok():
        return {"status": "ok"}

    async def kraken_ok():
        return {"status": "ok"}

    monkeypatch.setattr(diag, "_check_network", network_ok)
    monkeypatch.setattr(diag, "_check_kraken", kraken_ok)
    monkeypatch.setattr(diag, "_check_database", lambda: {"status": "ok"})
    monkeypatch.setattr(diag, "_check_bot", lambda: {"status": "ok"})

    status = await diag.run_full_check()

    assert status.overall == "critical"


@pytest.mark.asyncio
async def test_run_full_check_overall_is_warning_when_no_critical(monkeypatch):
    diag = DiagnosticManager()

    async def docker_ok():
        return {"status": "ok"}

    monkeypatch.setattr(diag, "_check_docker", docker_ok)
    monkeypatch.setattr(diag, "_check_system", lambda: {"status": "warning", "warning": "RAM élevée"})

    async def network_ok():
        return {"status": "ok"}

    async def kraken_ok():
        return {"status": "ok"}

    monkeypatch.setattr(diag, "_check_network", network_ok)
    monkeypatch.setattr(diag, "_check_kraken", kraken_ok)
    monkeypatch.setattr(diag, "_check_database", lambda: {"status": "ok"})
    monkeypatch.setattr(diag, "_check_bot", lambda: {"status": "ok"})

    status = await diag.run_full_check()

    assert status.overall == "warning"


@pytest.mark.asyncio
async def test_run_full_check_overall_is_healthy_when_all_ok(monkeypatch):
    diag = DiagnosticManager()

    async def check_ok_async():
        return {"status": "ok"}

    monkeypatch.setattr(diag, "_check_docker", check_ok_async)
    monkeypatch.setattr(diag, "_check_system", lambda: {"status": "ok"})
    monkeypatch.setattr(diag, "_check_network", check_ok_async)
    monkeypatch.setattr(diag, "_check_kraken", check_ok_async)
    monkeypatch.setattr(diag, "_check_database", lambda: {"status": "ok"})
    monkeypatch.setattr(diag, "_check_bot", lambda: {"status": "ok"})

    status = await diag.run_full_check()

    assert status.overall == "healthy"
