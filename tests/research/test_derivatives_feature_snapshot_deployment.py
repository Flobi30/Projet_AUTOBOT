from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit


def _deployment_file(name: str) -> str:
    return (ROOT / "deploy" / "systemd" / name).read_text(encoding="utf-8")


def test_derivatives_feature_snapshot_job_is_isolated_forward_research_only():
    script = _deployment_file("run-autobot-research-derivatives-feature-snapshot.sh")

    assert "materialize-derivatives-feature-snapshot" in script
    assert "--provenance-scope forward_capture_only" in script
    assert "AUTOBOT_DERIVATIVES_LOCK_PATH" in script
    assert "image provenance mismatch" in script
    assert "--network none" in script
    assert "--read-only" in script
    assert "--cap-drop ALL" in script
    assert "--security-opt no-new-privileges" in script
    assert '--volume "${REPO_DIR}/data/research:/app/data/research"' in script
    assert "--volume \"${REPO_DIR}/data:/app/data\"" not in script
    assert "--env-file" not in script
    assert "/.env:" not in script
    assert "sendorder" not in script.lower()
    assert "order_router" not in script
    assert "paper" not in script.lower()
    assert "live" not in script.lower()


def test_derivatives_feature_snapshot_timer_is_bounded_and_non_authorizing():
    service = _deployment_file("autobot-research-derivatives-feature-snapshot.service")
    timer = _deployment_file("autobot-research-derivatives-feature-snapshot.timer")

    assert "NoNewPrivileges=true" in service
    assert "TimeoutStartSec=5min" in service
    assert "ExecStart=/opt/Projet_AUTOBOT/deploy/systemd/run-autobot-research-derivatives-feature-snapshot.sh" in service
    assert "03:30:00 Europe/Paris" in timer
    assert "Persistent=true" in timer
    assert "RandomizedDelaySec=5min" in timer
