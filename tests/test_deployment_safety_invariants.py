from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_compose_enforces_research_shadow_execution_invariants():
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8")

    required = (
        "PAPER_EXECUTION_ADAPTER_ENABLED=false",
        "PAPER_DYNAMIC_CAPITAL_REBALANCE_ENABLED=false",
        "AUTOBOT_LEGACY_DIRECT_EXECUTION_ENABLED=false",
        "AUTOBOT_LEGACY_POSITION_ADD_ENABLED=false",
        "AUTOBOT_LEGACY_LEVERAGE_ACTIVATION_ENABLED=false",
        "ENABLE_INSTANCE_SPLIT_EXECUTOR=false",
        "COLONY_AUTO_SCALE_PAPER_CHILDREN=false",
        "COLONY_AUTO_LIVE_PROMOTION=false",
        "STRATEGY_ROUTER_LIVE_ENABLED=false",
    )

    for invariant in required:
        assert invariant in compose
