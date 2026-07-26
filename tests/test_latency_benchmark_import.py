from __future__ import annotations

import importlib
import logging
import sys

import pytest


pytestmark = pytest.mark.unit


def test_latency_benchmark_import_does_not_reconfigure_root_logging(monkeypatch):
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def record_basic_config(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(logging, "basicConfig", record_basic_config)
    module_name = "autobot.v2.benchmarks.latency_test"
    original_module = sys.modules.pop(module_name, None)
    try:
        importlib.import_module(module_name)
    finally:
        sys.modules.pop(module_name, None)
        if original_module is not None:
            sys.modules[module_name] = original_module

    assert calls == []
