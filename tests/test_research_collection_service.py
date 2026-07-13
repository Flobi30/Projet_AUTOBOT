from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_daily_research_service_runs_a_read_only_capability_scan_after_collection():
    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "systemd"
        / "run-autobot-research-collection.sh"
    ).read_text(encoding="utf-8")

    assert "exec docker run" not in script
    capability_section = script.split("data-capability-scan", maxsplit=1)[0]
    assert "autobot-research-capability-${RUN_ID}" in capability_section
    assert "--network none" in capability_section
    assert '"${REPO_DIR}/data:/app/data:ro"' in capability_section
    assert "--state-db data/autobot_state.db" in script
    assert "--data-roots data/research" in script
