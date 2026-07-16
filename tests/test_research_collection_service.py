from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_daily_research_service_runs_read_only_capability_and_scheduler_reports_after_collection():
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
    assert '"${REPO_DIR}/data/research:/app/data/research"' in script
    assert '"${REPO_DIR}/data:/app/data"' not in script
    assert '"${REPO_DIR}/data:/app/data:ro"' in capability_section
    assert "--state-db data/autobot_state.db" in script
    assert "--data-roots data/research" in script
    scheduler_section = script.split("alpha-hypothesis-scheduler", maxsplit=1)[0]
    assert "autobot-research-scheduler-${RUN_ID}" in scheduler_section
    assert "--no-memory-backfill" in script
    assert "--data-paths data/research/canonical/ohlcv" in script
    assert '"${REPO_DIR}/data/research:/app/data/research:ro"' in script


def test_daily_research_service_runs_one_isolated_bounded_research_coordinator_per_snapshot():
    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "systemd"
        / "run-autobot-research-collection.sh"
    ).read_text(encoding="utf-8")

    coordinator_section = script.split("autobot-research-coordinator-${RUN_ID}", maxsplit=1)[1]
    assert 'COORDINATOR_ENABLED="${AUTOBOT_BOUNDED_RESEARCH_COORDINATOR_ENABLED:-true}"' in script
    assert "autobot-research-coordinator-${RUN_ID}" in script
    assert "--network none" in coordinator_section
    assert '"${REPO_DIR}/data/research:/app/data/research"' in coordinator_section
    assert '"${REPO_DIR}/data:/app/data"' not in coordinator_section
    assert "--state-db" not in coordinator_section
    assert "--feature-snapshot-manifest" in coordinator_section
    assert "--commit \"${SOURCE_COMMIT}\"" in coordinator_section
    assert "--max-variants 3" in coordinator_section
