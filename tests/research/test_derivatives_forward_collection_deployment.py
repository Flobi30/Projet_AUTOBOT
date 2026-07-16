from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit


def test_derivatives_timer_is_bounded_public_research_only():
    script = (ROOT / "deploy/systemd/run-autobot-research-derivatives-collection.sh").read_text(encoding="utf-8")
    service = (ROOT / "deploy/systemd/autobot-research-derivatives.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy/systemd/autobot-research-derivatives.timer").read_text(encoding="utf-8")
    funding_service = (ROOT / "deploy/systemd/autobot-research-derivatives-funding.service").read_text(encoding="utf-8")
    funding_timer = (ROOT / "deploy/systemd/autobot-research-derivatives-funding.timer").read_text(encoding="utf-8")
    open_interest_service = (ROOT / "deploy/systemd/autobot-research-derivatives-open-interest.service").read_text(encoding="utf-8")
    open_interest_timer = (ROOT / "deploy/systemd/autobot-research-derivatives-open-interest.timer").read_text(encoding="utf-8")

    assert "collect-kraken-futures-derivatives" in script
    assert "--skip-funding" in script
    assert "--skip-candles" in script
    assert "--raw-retention-days 7" in script
    assert "AUTOBOT_DERIVATIVES_COLLECTION_MODE" in script
    assert "funding_refresh" in script
    assert "open_interest_refresh" in script
    assert "--collect-open-interest-history" in script
    assert "--open-interest-backfill-start-at" in script
    assert "--open-interest-backfill-end-at" in script
    assert "--assets \"BTC,ETH,SOL,XRP,ADA,LINK\"" in script
    assert "--volume \"${REPO_DIR}/data/research:/app/data/research\"" in script
    assert "--volume \"${REPO_DIR}/data:/app/data\"" not in script
    assert "--env-file" not in script
    assert "/.env:" not in script
    assert "--read-only" in script
    assert "--cap-drop ALL" in script
    assert "no-new-privileges" in script
    assert "sendorder" not in script.lower()
    assert "paper" not in script.lower()
    assert "ExecStart=/opt/Projet_AUTOBOT/deploy/systemd/run-autobot-research-derivatives-collection.sh" in service
    assert "NoNewPrivileges=true" in service
    assert "*:00,15,30,45:00" in timer
    assert "Persistent=true" in timer
    assert "AUTOBOT_DERIVATIVES_COLLECTION_MODE=funding_refresh" in funding_service
    assert "ExecStart=/opt/Projet_AUTOBOT/deploy/systemd/run-autobot-research-derivatives-collection.sh" in funding_service
    assert "NoNewPrivileges=true" in funding_service
    assert "00:05:00" in funding_timer
    assert "Persistent=true" in funding_timer
    assert "AUTOBOT_DERIVATIVES_COLLECTION_MODE=open_interest_refresh" in open_interest_service
    assert "ExecStart=/opt/Projet_AUTOBOT/deploy/systemd/run-autobot-research-derivatives-collection.sh" in open_interest_service
    assert "NoNewPrivileges=true" in open_interest_service
    assert "OnCalendar=hourly" in open_interest_timer
    assert "Persistent=true" in open_interest_timer
