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
