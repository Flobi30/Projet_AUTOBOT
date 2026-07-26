from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_compose_enforces_research_shadow_execution_invariants():
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8")

    required = (
        "AUTOBOT_OBSERVATION_ONLY_RUNTIME=true",
        "PAPER_TRADING=false",
        "PAPER_EXECUTION_ADAPTER_ENABLED=false",
        "PAPER_EXECUTION_ROUTER_ENABLED=false",
        "PAPER_TEST_TRADING_ENABLED=false",
        "PAPER_DYNAMIC_CAPITAL_REBALANCE_ENABLED=false",
        "AUTOBOT_LEGACY_DIRECT_EXECUTION_ENABLED=false",
        "AUTOBOT_LEGACY_POSITION_ADD_ENABLED=false",
        "AUTOBOT_LEGACY_LEVERAGE_ACTIVATION_ENABLED=false",
        "ENABLE_INSTANCE_SPLIT_EXECUTOR=false",
        "COLONY_PAPER_AUTOPILOT_ENABLED=false",
        "COLONY_AUTO_SCALE_PAPER_CHILDREN=false",
        "COLONY_AUTO_LIVE_PROMOTION=false",
        "STRATEGY_ROUTER_LIVE_ENABLED=false",
    )

    for invariant in required:
        assert invariant in compose

    assert "env_file:" not in compose
    assert "KRAKEN_API_KEY=${KRAKEN_API_KEY:-}" not in compose
    assert "KRAKEN_API_SECRET=${KRAKEN_API_SECRET:-}" not in compose
    assert "./.env:/app/.env:ro" not in compose
    assert "read_only: true" in compose
    assert "- ALL" in compose
    assert "no-new-privileges:true" in compose


def test_runtime_image_does_not_ship_an_env_file():
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY .env.example /app/.env" not in dockerfile


def test_read_only_runtime_writes_structured_logs_to_the_mounted_log_volume():
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8")

    assert "ENV AUTOBOT_LOG_FILE=/app/logs/autobot_async.log" in dockerfile
    assert "./logs:/app/logs" in compose
