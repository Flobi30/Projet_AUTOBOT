from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit


def test_canonical_microstructure_profile_timer_is_isolated_and_read_only():
    script = (ROOT / "deploy/systemd/run-autobot-research-microstructure-profile.sh").read_text(encoding="utf-8")
    service = (ROOT / "deploy/systemd/autobot-research-microstructure-profile.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy/systemd/autobot-research-microstructure-profile.timer").read_text(encoding="utf-8")

    assert "profile-canonical-microstructure" in script
    assert "--canonical-paths /app/data/research/canonical/microstructure" in script
    assert "--network none" in script
    assert "--volume \"${REPO_DIR}/data/research:/app/data/research:ro\"" in script
    assert "--volume \"${PROFILE_REPORT_DIR}:/app/data/research/reports/canonical_microstructure_profiles\"" in script
    assert "--env-file" not in script
    assert "/.env:" not in script
    assert "autobot_state.db" not in script
    assert "order_router" not in script
    assert "sendorder" not in script.lower()
    assert "--read-only" in script
    assert "--cap-drop ALL" in script
    assert "no-new-privileges" in script
    assert "image provenance mismatch" in script
    assert "chown 999:999 \"${CANONICAL_ROOT}\"" not in script
    assert "ExecStart=/opt/Projet_AUTOBOT/deploy/systemd/run-autobot-research-microstructure-profile.sh" in service
    assert "NoNewPrivileges=true" in service
    assert "*-*-* 03:13:00 UTC" in timer
    assert "Persistent=true" in timer
