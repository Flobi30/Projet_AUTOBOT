"""Global pytest bootstrap for deterministic local/CI imports."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent
_SRC_PATH = _REPO_ROOT / "src"

if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def pytest_configure(config) -> None:
    """Fail-fast with clear message if async plugin is missing locally."""
    try:
        import pytest_asyncio  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment guard
        raise pytest.UsageError(
            "pytest-asyncio is required for this repository. Install via "
            "`pip install -r requirements.txt`."
        ) from exc
