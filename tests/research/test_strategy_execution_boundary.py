"""Architecture guard: strategies and research adapters cannot execute trades.

The production runtime still contains legacy execution modules.  This test
keeps them outside strategy generation so any future promotion must continue
through the explicit AlphaSignal -> TargetPortfolio -> risk -> execution
boundary rather than introducing a direct shortcut.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


FORBIDDEN_EXECUTION_MODULES = frozenset(
    {
        "autobot.v2.order_router",
        "autobot.v2.order_queue_async",
        "autobot.v2.order_executor_async",
        "autobot.v2.paper_trading",
        "autobot.v2.paper.paper_trading_engine",
        "autobot.v2.kraken_client",
        "autobot.v2.signal_handler_async",
        "autobot.v2.orchestrator_async",
    }
)

FORBIDDEN_EXECUTION_CONTRACTS = frozenset({"OrderIntent", "OrderEvent", "FillEvent"})


def test_strategy_and_research_adapter_modules_cannot_bypass_the_central_execution_boundary() -> None:
    root = Path(__file__).resolve().parents[2]
    modules = tuple(sorted((root / "src" / "autobot" / "v2" / "strategies").glob("*.py"))) + tuple(
        sorted((root / "src" / "autobot" / "v2" / "research").glob("*adapter*.py"))
    )

    assert modules
    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        imports = _imports(tree)
        imported_names = _imported_names(tree)

        assert imports.isdisjoint(FORBIDDEN_EXECUTION_MODULES), module
        assert imported_names.isdisjoint(FORBIDDEN_EXECUTION_CONTRACTS), module


def _imports(tree: ast.AST) -> set[str]:
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    return imports


def _imported_names(tree: ast.AST) -> set[str]:
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
