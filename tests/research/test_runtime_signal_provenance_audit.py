import ast
import json
from pathlib import Path

import pytest

from autobot.v2.research.runtime_signal_provenance_audit import (
    REQUIRED_SHADOW_PROVENANCE_FIELDS,
    audit_runtime_signal_producers,
    write_runtime_signal_provenance_audit_report,
)


pytestmark = pytest.mark.unit


def _write_source(root: Path, name: str, text: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def test_static_audit_marks_legacy_buy_metadata_as_incomplete(tmp_path):
    _write_source(
        tmp_path,
        "legacy.py",
        """
from autobot.v2.strategies import TradingSignal, SignalType

def emit():
    return TradingSignal(type=SignalType.BUY, metadata={"strategy": "trend", "rsi": 54.0})
""",
    )

    report = audit_runtime_signal_producers(tmp_path)

    assert report.status == "BLOCKED_PENDING_CANONICAL_RUNTIME_PROVENANCE"
    finding = report.findings[0]
    assert finding.side == "BUY"
    assert finding.status == "BUY_PROVENANCE_INCOMPLETE"
    assert finding.metadata_keys == ("rsi", "strategy")
    assert finding.missing_required_fields == REQUIRED_SHADOW_PROVENANCE_FIELDS
    assert finding.to_dict()["shadow_runtime_eligible"] is False


def test_static_audit_never_treats_literal_keys_as_runtime_ready(tmp_path):
    metadata = ", ".join(f'"{field}": "fixture"' for field in REQUIRED_SHADOW_PROVENANCE_FIELDS)
    _write_source(
        tmp_path,
        "complete_keys.py",
        f"""
from autobot.v2.strategies import TradingSignal, SignalType

def emit():
    return TradingSignal(type=SignalType.BUY, metadata={{{metadata}}})
""",
    )

    report = audit_runtime_signal_producers(tmp_path)

    finding = report.findings[0]
    assert finding.status == "BUY_PROVENANCE_UNVERIFIED"
    assert finding.missing_required_fields == ()
    assert finding.to_dict()["shadow_runtime_eligible"] is False


def test_static_audit_keeps_dynamic_metadata_and_sell_outside_shadow_eligibility(tmp_path):
    _write_source(
        tmp_path,
        "mixed.py",
        """
from autobot.v2.strategies import TradingSignal, SignalType

def emit(metadata):
    first = TradingSignal(type=SignalType.BUY, metadata=metadata)
    second = TradingSignal(type=SignalType.SELL, metadata={"close_all": True})
    return first, second
""",
    )

    report = audit_runtime_signal_producers(tmp_path)

    assert [item.status for item in report.findings] == [
        "BUY_PROVENANCE_UNKNOWN",
        "NOT_BUY_NOT_ASSESSED",
    ]
    assert all(item.to_dict()["order_created"] is False for item in report.findings)


def test_static_audit_keeps_retired_grid_sources_in_inventory_not_migration_counts(tmp_path):
    _write_source(
        tmp_path,
        "grid.py",
        """
from autobot.v2.strategies import TradingSignal, SignalType

def emit():
    return TradingSignal(type=SignalType.BUY, metadata={"strategy": "grid"})
""",
    )

    report = audit_runtime_signal_producers(tmp_path)

    assert report.status == "NO_ACTIONABLE_BUY_PRODUCERS_FOUND"
    assert report.findings[0].status == "RETIRED_SOURCE_NOT_ACTIONABLE"
    assert report.findings[0].retired_source is True
    assert report.to_dict()["summary"]["retired_buy_signal_constructors"] == 1
    assert report.to_dict()["summary"]["actionable_buy_signal_constructors"] == 0


def test_static_audit_report_is_compact_research_output(tmp_path):
    _write_source(
        tmp_path / "source",
        "producer.py",
        "from autobot.v2.strategies import TradingSignal, SignalType\n"
        "x = TradingSignal(type=SignalType.BUY, metadata={})\n",
    )
    report = audit_runtime_signal_producers(tmp_path / "source")
    path = write_runtime_signal_provenance_audit_report(report, tmp_path / "reports", run_id="audit fixture")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "audit_fixture_runtime_signal_provenance.json"
    assert payload["research_only"] is True
    assert payload["paper_capital_allowed"] is False
    assert payload["live_allowed"] is False
    assert payload["automatic_promotion_allowed"] is False


def test_runtime_signal_provenance_audit_has_no_runtime_or_execution_imports():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/autobot/v2/research/runtime_signal_provenance_audit.py").read_text(encoding="utf-8"))
    forbidden = {
        "autobot.v2.signal_handler_async",
        "autobot.v2.order_router",
        "autobot.v2.paper_trading",
        "autobot.v2.order_executor",
        "autobot.v2.orchestrator_async",
    }
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
    assert imports.isdisjoint(forbidden)
