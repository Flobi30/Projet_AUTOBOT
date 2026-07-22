from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def _deployment_file(name: str) -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / "deploy" / "systemd" / name).read_text(encoding="utf-8")


def test_snapshot_audit_wrapper_is_disabled_and_has_no_runtime_or_execution_surface():
    script = _deployment_file("run-autobot-strategy-artifact-readiness-snapshot-audit.sh")

    assert 'AUTOBOT_STRATEGY_ARTIFACT_READINESS_AUDIT_ENABLED:-false' in script
    assert "--network none" in script
    assert "--read-only" in script
    assert "--cap-drop ALL" in script
    assert "--security-opt no-new-privileges" in script
    assert '"${REPO_DIR}/data/research:/app/data/research:ro"' in script
    assert "--tmpfs /tmp:rw,noexec,nosuid,size=128m" in script
    assert "strategy-artifact-readiness-snapshot-audit" in script
    assert "strategy-artifact-readiness-audit" in script
    assert "autobot_state.db" not in script
    assert ".env" not in script
    assert "sendorder" not in script.lower()
    assert "paper_trading" not in script.lower()


def test_snapshot_audit_systemd_units_remain_disabled_until_operator_approval():
    service = _deployment_file("autobot-strategy-artifact-readiness-audit.service")
    timer = _deployment_file("autobot-strategy-artifact-readiness-audit.timer")

    assert "Environment=AUTOBOT_STRATEGY_ARTIFACT_READINESS_AUDIT_ENABLED=false" in service
    assert "NoNewPrivileges=true" in service
    assert "ExecStart=/opt/Projet_AUTOBOT/deploy/systemd/run-autobot-strategy-artifact-readiness-snapshot-audit.sh" in service
    assert "OnCalendar=*-*-* 02:50:00" in timer
    assert "Persistent=true" in timer
