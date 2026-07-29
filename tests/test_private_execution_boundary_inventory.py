"""Static inventory for every production path that can reach Kraken private APIs.

The active AUTOBOT programme is intentionally research/shadow-only.  These
checks keep direct legacy method calls from becoming an unreviewed escape hatch
when a future refactor changes constructor or router behaviour.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


ROOT = Path(__file__).resolve().parents[1]


def _functions_by_name(path: Path) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _first_executable_statement(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> ast.stmt:
    body = list(function.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body.pop(0)
    assert body, f"{function.name} has no executable body"
    return body[0]


@pytest.mark.parametrize(
    ("relative_path", "function_name", "guard_name"),
    (
        ("src/autobot/order_manager.py", "_get_client", "reject_private_execution_component"),
        ("src/autobot/v2/instance.py", "_cancel_all_orders", "reject_private_execution_component"),
        ("src/autobot/v2/instance.py", "_close_all_positions_market", "reject_private_execution_component"),
        ("src/autobot/v2/order_executor.py", "_get_client", "reject_private_execution_component"),
        ("src/autobot/v2/order_executor_async.py", "_query_private", "reject_private_execution_component"),
        ("src/autobot/v2/orchestrator_async.py", "_get_available_capital_real", "reject_private_execution_component"),
        ("src/autobot/v2/orchestrator.py", "_get_available_capital_real", "reject_legacy_synchronous_runtime"),
    ),
)
def test_private_kraken_boundary_guard_is_the_first_executable_operation(
    relative_path: str,
    function_name: str,
    guard_name: str,
):
    function = _functions_by_name(ROOT / relative_path)[function_name]
    statement = _first_executable_statement(function)

    assert isinstance(statement, ast.Expr)
    assert isinstance(statement.value, ast.Call)
    assert isinstance(statement.value.func, ast.Name)
    assert statement.value.func.id == guard_name


def test_private_kraken_query_inventory_has_no_unmapped_production_file():
    """Every direct private Kraken call remains behind a tested boundary."""

    expected_paths = {
        "src/autobot/order_manager.py",
        "src/autobot/v2/instance.py",
        "src/autobot/v2/orchestrator.py",
        "src/autobot/v2/orchestrator_async.py",
        "src/autobot/v2/order_executor.py",
        "src/autobot/v2/order_executor_async.py",
    }
    found_paths = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src").rglob("*.py")
        if "tests" not in path.parts
        and (
            ".query_private" in path.read_text(encoding="utf-8")
            or "def _query_private" in path.read_text(encoding="utf-8")
        )
    }

    assert found_paths == expected_paths
