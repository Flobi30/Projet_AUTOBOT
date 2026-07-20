from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit


def test_forward_microstructure_timer_is_isolated_public_research_only():
    script = (ROOT / "deploy/systemd/run-autobot-research-microstructure-collection.sh").read_text(encoding="utf-8")
    service = (ROOT / "deploy/systemd/autobot-research-microstructure.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy/systemd/autobot-research-microstructure.timer").read_text(encoding="utf-8")

    assert "collect-microstructure-forward" in script
    assert "--symbols \"${SYMBOLS}\"" in script
    assert "--volume \"${REPO_DIR}/data/research:/app/data/research\"" in script
    assert "${REPO_DIR}/data:/app/data" not in script
    assert "--env-file" not in script
    assert "/.env:" not in script
    assert "--read-only" in script
    assert "--cap-drop ALL" in script
    assert "no-new-privileges" in script
    assert "image provenance mismatch" in script
    assert "sendorder" not in script.lower()
    assert "ExecStart=/opt/Projet_AUTOBOT/deploy/systemd/run-autobot-research-microstructure-collection.sh" in service
    assert "NoNewPrivileges=true" in service
    assert "*:07,22,37,52:00 UTC" in timer
    assert "Persistent=true" in timer
