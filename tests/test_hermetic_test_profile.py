"""Keep local and container regression commands on one hermetic test profile."""

from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_default_pytest_profile_excludes_non_hermetic_markers():
    root = Path(__file__).resolve().parents[1]
    pytest_ini = (root / "pytest.ini").read_text(encoding="utf-8")

    assert 'addopts = --strict-markers -m "not performance and not external and not e2e"' in pytest_ini


def test_container_test_command_reuses_default_hermetic_pytest_profile():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile.test").read_text(encoding="utf-8")

    assert 'CMD ["python", "-m", "pytest", "-q"]' in dockerfile
    assert "-m\", \"unit" not in dockerfile


def test_agents_document_public_collection_as_a_separate_network_exception():
    root = Path(__file__).resolve().parents[1]
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")

    assert "Public-data collectors are the explicit exception" in agents
    assert "public endpoints" in agents
