"""Regression tests proving the production entry point avoids sync legacy engines."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from autobot.v2.instance import InstanceStatus as LegacyInstanceStatus
from autobot.v2.instance_models import InstanceStatus
from autobot.v2.instance_config import InstanceConfig
from autobot.v2.orchestrator import InstanceConfig as LegacyInstanceConfig


pytestmark = pytest.mark.unit


def test_legacy_imports_reexport_passive_shared_contracts():
    """Existing import sites keep their contracts without owning the runtime path."""

    assert LegacyInstanceStatus is InstanceStatus
    assert LegacyInstanceConfig is InstanceConfig


def test_async_main_import_does_not_load_sync_execution_engines():
    """A clean production import must not load threaded/order-capable legacy code."""

    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    source_root = str(project_root / "src")
    env["PYTHONPATH"] = source_root + os.pathsep + env.get("PYTHONPATH", "")
    code = (
        "import sys; import autobot.v2.main_async; "
        "forbidden = {'autobot.v2.orchestrator', 'autobot.v2.instance', 'autobot.v2.reconciliation'}; "
        "loaded = forbidden.intersection(sys.modules); "
        "raise SystemExit('legacy runtime modules loaded: ' + repr(sorted(loaded)) if loaded else 0)"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

