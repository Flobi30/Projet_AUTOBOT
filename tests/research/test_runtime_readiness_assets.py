from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_runtime_image_includes_versioned_layer_coverage_for_readiness_dossier():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "COPY docs/architecture/ /app/docs/architecture/" in dockerfile
    assert Path("docs/architecture/layer_coverage.json").is_file()
