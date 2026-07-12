from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit


def test_derivatives_timer_is_bounded_public_research_only():
    script = (ROOT / "deploy/systemd/run-autobot-research-derivatives-collection.sh").read_text(encoding="utf-8")
    service = (ROOT / "deploy/systemd/autobot-research-derivatives.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy/systemd/autobot-research-derivatives.timer").read_text(encoding="utf-8")

    assert "collect-kraken-futures-derivatives" in script
    assert "--skip-funding" in script
    assert "--skip-candles" in script
    assert "--assets \"BTC,ETH,SOL,XRP,ADA,LINK\"" in script
    assert "--volume \"${REPO_DIR}/data:/app/data\"" in script
    assert "--env-file" not in script
    assert "/.env:" not in script
    assert "--read-only" in script
    assert "--cap-drop ALL" in script
    assert "no-new-privileges" in script
    assert "sendorder" not in script.lower()
    assert "paper" not in script.lower()
    assert "ExecStart=/opt/Projet_AUTOBOT/deploy/systemd/run-autobot-research-derivatives-collection.sh" in service
    assert "NoNewPrivileges=true" in service
    assert "*:00,15,30,45:00 UTC" in timer
    assert "Persistent=true" in timer
