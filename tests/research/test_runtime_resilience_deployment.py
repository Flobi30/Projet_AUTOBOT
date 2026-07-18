from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def _deployment_file(name: str) -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / "deploy" / "systemd" / name).read_text(encoding="utf-8")


def test_runtime_resilience_audit_script_has_a_read_only_non_authorizing_boundary():
    script = _deployment_file("run-autobot-runtime-resilience-audit.sh")

    assert 'AUTOBOT_RUNTIME_RESILIENCE_AUDIT_ENABLED:-false' in script
    assert 'curl --fail --silent --max-time 5 http://127.0.0.1:8080/health' in script
    assert "--network none" in script
    assert "--read-only" in script
    assert "--cap-drop ALL" in script
    assert "--security-opt no-new-privileges" in script
    assert '"${REPO_DIR}/data:/app/data:ro"' in script
    assert "runtime-resilience-audit" in script
    assert "--websocket-status" in script
    assert "PAPER_EXECUTION_ADAPTER_ENABLED" not in script
    assert ".env" not in script
    assert "sendorder" not in script.lower()
    assert "order_router" not in script
    assert "\nrm " not in script


def test_runtime_resilience_audit_systemd_timer_is_isolated_and_operational_only():
    service = _deployment_file("autobot-runtime-resilience-audit.service")
    timer = _deployment_file("autobot-runtime-resilience-audit.timer")

    assert "Environment=AUTOBOT_RUNTIME_RESILIENCE_AUDIT_ENABLED=true" in service
    assert "NoNewPrivileges=true" in service
    assert "ExecStart=/opt/Projet_AUTOBOT/deploy/systemd/run-autobot-runtime-resilience-audit.sh" in service
    assert "TimeoutStartSec=2min" in service
    assert "KillMode=control-group" in service
    assert "TimeoutStopSec=30s" in service
    assert "ExecStop=/bin/sh -c '/usr/bin/docker ps -q --filter label=autobot.component=runtime-resilience-audit" in service
    assert "ExecStopPost=/bin/sh -c '/usr/bin/docker ps -aq --filter label=autobot.component=runtime-resilience-audit" in service
    cleanup_lines = [line for line in service.splitlines() if line.startswith("ExecStop")]
    assert all("autobot-v2" not in line for line in cleanup_lines)
    assert all("docker compose" not in line.lower() for line in cleanup_lines)
    assert "OnBootSec=2min" in timer
    assert "OnUnitActiveSec=5min" in timer
    assert "Persistent=true" in timer
