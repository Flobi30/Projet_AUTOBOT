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
    assert "--capability-data-paths data/research/canonical/ohlcv,data/research/manifests" in script
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
    assert "--capability-data-paths data/research/canonical/ohlcv,data/research/manifests" in coordinator_section
    assert "--commit \"${SOURCE_COMMIT}\"" in coordinator_section
    assert "--image-commit \"${IMAGE_COMMIT}\"" in coordinator_section
    assert "--max-variants 3" in coordinator_section


def test_daily_research_service_rejects_stale_or_unverifiable_image_before_collection():
    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "systemd"
        / "run-autobot-research-collection.sh"
    ).read_text(encoding="utf-8")

    collection_section = script.split("docker run --rm", maxsplit=1)[0]
    assert 'IMAGE_COMMIT="$(docker image inspect' in collection_section
    assert "'{{ index .Config.Labels \"org.opencontainers.image.revision\" }}'" in collection_section
    assert '"${IMAGE_COMMIT}" != "${SOURCE_COMMIT}"' in collection_section
    assert "image provenance mismatch" in collection_section


def test_daily_research_service_stop_path_cleans_only_its_labelled_containers():
    root = Path(__file__).resolve().parents[1]
    script = (root / "deploy" / "systemd" / "run-autobot-research-collection.sh").read_text(encoding="utf-8")
    unit = (root / "deploy" / "systemd" / "autobot-research-data.service").read_text(encoding="utf-8")

    assert script.count('--label "autobot.job=research-daily"') == 4
    assert "KillMode=control-group" in unit
    assert "TimeoutStopSec=45s" in unit
    assert "ExecStop=/bin/sh -c" in unit
    assert "label=autobot.job=research-daily" in unit
    assert "docker stop --timeout 20" in unit
    assert "ExecStopPost=/bin/sh -c" in unit
    assert "autobot-v2" not in unit
    assert "docker compose" not in unit
