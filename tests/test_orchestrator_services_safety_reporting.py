import asyncio

import pytest

from autobot.v2.orchestrator_services import ReportingService, SafetyService


pytestmark = pytest.mark.integration


class _Logger:
    def __init__(self):
        self.infos = []
        self.errors = []
        self.warnings = []

    def info(self, msg, *args):
        self.infos.append(msg % args if args else msg)

    def error(self, msg, *args):
        self.errors.append(msg % args if args else msg)

    def warning(self, msg, *args):
        self.warnings.append(msg % args if args else msg)


class _SafetyGuard:
    def __init__(self):
        self.emergency_mode = False
        self.reset_calls = 0

    def check_performance_budget(self, _cycle_ms):
        return False

    def reset_emergency(self):
        self.reset_calls += 1
        self.emergency_mode = False


class _RobustnessGuard:
    def __init__(self):
        self.values = []

    def set_emergency_mode(self, value):
        self.values.append(bool(value))


class _Reporter:
    def __init__(self):
        self.calls = 0

    def generate_report(self):
        self.calls += 1
        return {"date": "2026-04-22", "total_trades": 3}


@pytest.mark.asyncio
async def test_safety_service_emergency_and_monitor_cycle_health():
    logger = _Logger()
    safety_guard = _SafetyGuard()
    robustness_guard = _RobustnessGuard()
    hardening_flags = {
        "enable_validation_guard": True,
        "enable_sentiment": True,
        "enable_ml": True,
        "enable_xgboost": True,
        "enable_onchain": True,
    }
    service = SafetyService(
        safety_guard=safety_guard,
        robustness_guard=robustness_guard,
        hardening_flags=hardening_flags,
        reset_flag_reader=lambda: False,
    )

    assert service.activate_emergency_mode("budget", logger) is True
    assert safety_guard.emergency_mode is True
    assert robustness_guard.values[-1] is True
    assert hardening_flags["enable_ml"] is False

    running = True
    activated = asyncio.Event()

    def _on_activate(_reason):
        nonlocal running
        running = False
        activated.set()

    await service.monitor_cycle_health(
        running=lambda: running,
        loop_metrics={"process_cycle_ms": 1000.0},
        on_activate=_on_activate,
        logger=logger,
        interval_seconds=0.01,
    )

    assert activated.is_set()


@pytest.mark.asyncio
async def test_reporting_service_daily_loop_calls_report(monkeypatch):
    logger = _Logger()
    reporter = _Reporter()
    service = ReportingService(reporter)

    running = True

    async def _fake_sleep(_seconds):
        nonlocal running
        running = False

    monkeypatch.setattr("autobot.v2.orchestrator_services.asyncio.sleep", _fake_sleep)

    await service.run_daily_report_loop(running=lambda: running, logger=logger)

    assert reporter.calls == 1
    assert any("Daily report généré" in line for line in logger.infos)
