from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_autobot_image_carries_an_explicit_source_revision_label():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")

    assert "ARG AUTOBOT_BUILD_COMMIT=unverified" in dockerfile
    assert "LABEL org.opencontainers.image.revision=${AUTOBOT_BUILD_COMMIT}" in dockerfile
    assert "ENV AUTOBOT_BUILD_COMMIT=${AUTOBOT_BUILD_COMMIT}" in dockerfile
    assert "AUTOBOT_BUILD_COMMIT: ${AUTOBOT_BUILD_COMMIT:-unverified}" in compose


def test_rebuild_helper_binds_image_label_to_clean_checkout_commit():
    root = Path(__file__).resolve().parents[1]
    script = (root / "deploy" / "rebuild-autobot-image.sh").read_text(encoding="utf-8")

    assert "BUILD_INPUT_PATHS=(" in script
    assert 'git -C "${REPO_DIR}" diff --quiet -- "${BUILD_INPUT_PATHS[@]}"' in script
    assert 'git -C "${REPO_DIR}" diff --cached --quiet -- "${BUILD_INPUT_PATHS[@]}"' in script
    assert 'git -C "${REPO_DIR}" ls-files --others --exclude-standard -- "${BUILD_INPUT_PATHS[@]}"' in script
    assert "reports/research" not in script
    assert 'SOURCE_COMMIT="$(git -C "${REPO_DIR}" rev-parse --verify HEAD)"' in script
    assert 'AUTOBOT_BUILD_COMMIT="${SOURCE_COMMIT}"' in script
    assert "'{{ index .Config.Labels \"org.opencontainers.image.revision\" }}'" in script
    assert '"${IMAGE_COMMIT}" != "${SOURCE_COMMIT}"' in script
