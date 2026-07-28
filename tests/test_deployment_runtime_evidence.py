from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_runtime_evidence_script_is_read_only_and_requires_strict_safety_proof():
    root = Path(__file__).resolve().parents[1]
    script = (root / "deploy" / "verify-autobot-runtime-evidence.sh").read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    assert "refs/remotes/origin/master" in script
    assert "Refusing deployment evidence" in script
    assert "docker compose" not in script
    assert "docker build" not in script
    assert "docker restart" not in script
    assert "docker stop" not in script
    assert "sendorder" not in script.lower()
    assert "KRAKEN_API_KEY" not in script
    assert "KRAKEN_API_SECRET" not in script
    assert "AUTOBOT_OBSERVATION_ONLY_RUNTIME=true" in script
    assert "PAPER_TRADING=false" in script
    assert "PAPER_EXECUTION_ADAPTER_ENABLED=false" in script
    assert "COLONY_AUTO_LIVE_PROMOTION=false" in script
    assert "STRATEGY_ROUTER_LIVE_ENABLED=false" in script
    assert "LIVE_TRADING_CONFIRMATION=false" in script
    assert "RuntimeDeploymentEvidence" in script
    assert '"container_healthy":true' in script
    assert '"paper_capital_disabled":true' in script
    assert '"live_disabled":true' in script
