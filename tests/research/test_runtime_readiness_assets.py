from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_runtime_image_includes_versioned_layer_coverage_for_readiness_dossier():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "COPY docs/architecture/ /app/docs/architecture/" in dockerfile
    assert Path("docs/architecture/layer_coverage.json").is_file()


def test_archived_paper_operations_guide_contains_no_activation_or_credential_procedure():
    guide = Path("docs/PAPER_TRADING_OPERATIONS.md").read_text(encoding="utf-8")

    assert "ARCHIVED / NON-OPERATIONAL" in guide
    assert "READY_FOR_HUMAN_PAPER_REVIEW" in guide
    for forbidden in (
        "PAPER_TRADING=true",
        "PREFLIGHT_ONLY=",
        "KRAKEN_API_KEY",
        "KRAKEN_API_SECRET",
        "paper_ops.py start-guide",
        "python -u src/autobot/v2/main_async.py",
    ):
        assert forbidden not in guide


def test_default_configuration_and_top_level_guides_remain_observation_only():
    environment = Path(".env.example").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    live_guide = Path("docs/LIVE_PROMOTION_GATES.md").read_text(encoding="utf-8")

    for required in (
        "AUTOBOT_OBSERVATION_ONLY_RUNTIME=true",
        "PAPER_TRADING=false",
        "PAPER_EXECUTION_ADAPTER_ENABLED=false",
        "PAPER_EXECUTION_ROUTER_ENABLED=false",
        "PAPER_TEST_TRADING_ENABLED=false",
        "AUTOBOT_REAL_ORDER_EXECUTION_ENABLED=false",
        "COLONY_AUTO_LIVE_PROMOTION=false",
        "STRATEGY_ROUTER_LIVE_ENABLED=false",
        "LIVE_TRADING_CONFIRMATION=false",
    ):
        assert required in environment

    assert "PAPER_TRADING=true" not in environment
    assert "\nKRAKEN_API_KEY=" not in environment
    assert "\nKRAKEN_API_SECRET=" not in environment
    assert "PAPER_TRADING=true" not in readme
    assert "ARCHIVED / NON-OPERATIONAL" in live_guide
    assert "PAPER_TRADING=true" not in live_guide
    assert "KRAKEN_API_KEY" not in readme
