"""Ensure retired operator helpers cannot reintroduce paper or secret workflows."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest


pytestmark = pytest.mark.unit


def test_retired_preflight_exits_before_runtime_or_secret_handling():
    root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, "test_preflight.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "retired_from_execution" in result.stdout


def test_retired_operator_sources_contain_no_activation_or_credential_guidance():
    root = Path(__file__).resolve().parents[1]
    paths = (
        root / "test_preflight.py",
        root / "setup-vps.sh",
    )

    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert "retired_from_execution" in content
        assert "KRAKEN_API_KEY" not in content
        assert "KRAKEN_API_SECRET" not in content
        assert "PAPER_TRADING=true" not in content

    paper_ops = (root / "tools/paper_ops.py").read_text(encoding="utf-8")
    assert "PAPER_TRADING=true" not in paper_ops
    assert "KRAKEN_API_KEY" not in paper_ops
    assert "KRAKEN_API_SECRET" not in paper_ops
    assert "retired_from_execution" in paper_ops


def test_retired_vps_setup_cannot_prompt_or_write_an_environment_file():
    root = Path(__file__).resolve().parents[1]
    content = (root / "setup-vps.sh").read_text(encoding="utf-8")

    assert "read -" not in content
    assert "cat >" not in content
    assert "docker-compose up" not in content
