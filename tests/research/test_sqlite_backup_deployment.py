from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def _deployment_file(name: str) -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / "deploy" / "systemd" / name).read_text(encoding="utf-8")


def test_sqlite_backup_script_is_disabled_by_default_and_has_a_narrow_mount_boundary():
    script = _deployment_file("run-autobot-sqlite-backup.sh")

    assert 'AUTOBOT_SQLITE_BACKUP_ENABLED:-false' in script
    assert 'AUTOBOT_SQLITE_BACKUP_EXTERNAL_POLICY_APPROVED:-false' in script
    assert "--network none" in script
    assert "--read-only" in script
    assert "--cap-drop ALL" in script
    assert "--security-opt no-new-privileges" in script
    assert '"${REPO_DIR}/data:/app/data:ro"' in script
    assert '"${BACKUP_DIR}:/app/backups"' in script
    assert "--source /app/data/autobot_state.db" in script
    assert "--backup-path" in script
    assert ".env" not in script
    assert "sendorder" not in script.lower()
    assert "\nrm " not in script


def test_sqlite_backup_systemd_units_stay_disabled_until_operator_approval():
    service = _deployment_file("autobot-sqlite-backup.service")
    timer = _deployment_file("autobot-sqlite-backup.timer")

    assert "Environment=AUTOBOT_SQLITE_BACKUP_ENABLED=false" in service
    assert "Environment=AUTOBOT_SQLITE_BACKUP_EXTERNAL_POLICY_APPROVED=false" in service
    assert "NoNewPrivileges=true" in service
    assert "ExecStart=/opt/Projet_AUTOBOT/deploy/systemd/run-autobot-sqlite-backup.sh" in service
    assert "OnCalendar=*-*-* 03:15:00" in timer
    assert "Persistent=true" in timer
