from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


def test_no_wildcard_imports_in_autobot_v2() -> None:
    base_dir = Path(__file__).resolve().parents[1] / "src" / "autobot" / "v2"
    offenders: list[str] = []

    for py_file in sorted(base_dir.rglob("*.py")):
        for lineno, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), start=1):
            if " import *" in line:
                offenders.append(f"{py_file.relative_to(base_dir)}:{lineno}")

    assert not offenders, (
        "Wildcard imports are forbidden in src/autobot/v2/. "
        f"Replace with explicit imports: {', '.join(offenders)}"
    )
