"""Static, research-only audit of legacy runtime signal provenance.

The historical strategy classes still emit :class:`TradingSignal` objects with
local indicator metadata.  That metadata must never be mistaken for the
immutable market, feature and artifact evidence required by the canonical
shadow boundary.  This module reads Python source with :mod:`ast`; it neither
imports strategy code nor starts runtime, writes a ledger, or creates an
order.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


REQUIRED_SHADOW_PROVENANCE_FIELDS = (
    "strategy_id",
    "strategy_version",
    "data_snapshot_id",
    "data_available_at",
    "net_expected_edge_bps",
    "shadow_notional_eur",
    "feature_versions",
    "verified_feature_vectors",
    "strategy_artifact",
    "market_identity",
)


@dataclass(frozen=True)
class RuntimeSignalProvenanceFinding:
    """One static ``TradingSignal`` producer and its known provenance gap."""

    source_path: str
    line: int
    side: str
    status: str
    metadata_kind: str
    metadata_keys: tuple[str, ...]
    missing_required_fields: tuple[str, ...]
    dynamic_metadata: bool
    retired_source: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "line": self.line,
            "side": self.side,
            "status": self.status,
            "metadata_kind": self.metadata_kind,
            "metadata_keys": list(self.metadata_keys),
            "missing_required_fields": list(self.missing_required_fields),
            "dynamic_metadata": self.dynamic_metadata,
            "retired_source": self.retired_source,
            "shadow_runtime_eligible": False,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "order_created": False,
        }


@dataclass(frozen=True)
class RuntimeSignalProvenanceAuditReport:
    """Deterministic evidence that legacy signal emitters remain quarantined."""

    source_root: str
    generated_at: str
    findings: tuple[RuntimeSignalProvenanceFinding, ...]
    parse_errors: tuple[str, ...] = ()

    @property
    def buy_findings(self) -> tuple[RuntimeSignalProvenanceFinding, ...]:
        return tuple(item for item in self.findings if item.side == "BUY")

    @property
    def actionable_buy_findings(self) -> tuple[RuntimeSignalProvenanceFinding, ...]:
        return tuple(item for item in self.buy_findings if not item.retired_source)

    @property
    def status(self) -> str:
        if self.parse_errors:
            return "AUDIT_INCOMPLETE"
        if self.actionable_buy_findings:
            return "BLOCKED_PENDING_CANONICAL_RUNTIME_PROVENANCE"
        return "NO_ACTIONABLE_BUY_PRODUCERS_FOUND"

    def to_dict(self) -> dict[str, Any]:
        buy_findings = self.buy_findings
        actionable_buy_findings = self.actionable_buy_findings
        return {
            "audit": "runtime_signal_provenance/v1",
            "status": self.status,
            "source_root": self.source_root,
            "generated_at": self.generated_at,
            "required_shadow_provenance_fields": list(REQUIRED_SHADOW_PROVENANCE_FIELDS),
            "summary": {
                "signal_constructors": len(self.findings),
                "buy_signal_constructors": len(buy_findings),
                "retired_signal_constructors": sum(item.retired_source for item in self.findings),
                "retired_buy_signal_constructors": sum(item.retired_source for item in buy_findings),
                "actionable_buy_signal_constructors": len(actionable_buy_findings),
                "buy_provenance_incomplete": sum(
                    item.status == "BUY_PROVENANCE_INCOMPLETE" for item in actionable_buy_findings
                ),
                "buy_provenance_unknown": sum(
                    item.status == "BUY_PROVENANCE_UNKNOWN" for item in actionable_buy_findings
                ),
                "buy_provenance_unverified": sum(
                    item.status == "BUY_PROVENANCE_UNVERIFIED" for item in actionable_buy_findings
                ),
                "parse_errors": len(self.parse_errors),
            },
            "findings": [item.to_dict() for item in self.findings],
            "parse_errors": list(self.parse_errors),
            "research_only": True,
            "shadow_runtime_started": False,
            "paper_capital_allowed": False,
            "live_allowed": False,
            "automatic_promotion_allowed": False,
            "order_created": False,
            "notes": [
                "Static key presence is not proof of immutable canonical provenance.",
                "No finding is shadow-runtime eligible: artifact, verified vector and mandate checks remain dynamic fail-closed gates.",
                "Known retired Grid source files are reported for inventory but excluded from actionable migration counts.",
                "This audit does not import strategy modules or modify runtime state.",
            ],
        }


def audit_runtime_signal_producers(source_root: str | Path) -> RuntimeSignalProvenanceAuditReport:
    """Inspect source only and report why legacy BUY signals cannot be promoted.

    The audit deliberately treats a complete static key set as *unverified*.
    Runtime eligibility additionally requires an immutable artifact, an exact
    published vector and an active non-authorizing mandate, which source code
    cannot prove.
    """

    root = Path(source_root)
    if not root.is_dir():
        raise ValueError(f"source_root_not_directory:{root}")

    findings: list[RuntimeSignalProvenanceFinding] = []
    parse_errors: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            parse_errors.append(f"{path}:{type(exc).__name__}")
            continue
        findings.extend(_findings_for_tree(tree, path, root))

    return RuntimeSignalProvenanceAuditReport(
        source_root=str(root),
        generated_at=datetime.now(timezone.utc).isoformat(),
        findings=tuple(sorted(findings, key=lambda item: (item.source_path, item.line))),
        parse_errors=tuple(sorted(parse_errors)),
    )


def write_runtime_signal_provenance_audit_report(
    report: RuntimeSignalProvenanceAuditReport,
    output_dir: str | Path,
    *,
    run_id: str,
) -> Path:
    """Write a compact research report; never write runtime data or a ledger."""

    normalized_run_id = _safe_run_id(run_id)
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{normalized_run_id}_runtime_signal_provenance.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _findings_for_tree(
    tree: ast.AST,
    path: Path,
    root: Path,
) -> list[RuntimeSignalProvenanceFinding]:
    result: list[RuntimeSignalProvenanceFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_trading_signal_call(node):
            continue
        side = _side_from_call(node)
        metadata_kind, metadata_keys, dynamic_metadata = _metadata_from_call(node)
        missing = tuple(field for field in REQUIRED_SHADOW_PROVENANCE_FIELDS if field not in metadata_keys)
        retired_source = _is_retired_grid_source(path, root)
        if retired_source:
            status = "RETIRED_SOURCE_NOT_ACTIONABLE"
        elif side != "BUY":
            status = "NOT_BUY_NOT_ASSESSED"
        elif dynamic_metadata:
            status = "BUY_PROVENANCE_UNKNOWN"
        elif missing:
            status = "BUY_PROVENANCE_INCOMPLETE"
        else:
            status = "BUY_PROVENANCE_UNVERIFIED"
        result.append(
            RuntimeSignalProvenanceFinding(
                source_path=path.relative_to(root).as_posix(),
                line=int(getattr(node, "lineno", 0)),
                side=side,
                status=status,
                metadata_kind=metadata_kind,
                metadata_keys=metadata_keys,
                missing_required_fields=missing,
                dynamic_metadata=dynamic_metadata,
                retired_source=retired_source,
            )
        )
    return result


def _is_trading_signal_call(node: ast.Call) -> bool:
    function = node.func
    return isinstance(function, ast.Name) and function.id == "TradingSignal"


def _side_from_call(node: ast.Call) -> str:
    value = next((item.value for item in node.keywords if item.arg == "type"), None)
    if isinstance(value, ast.Attribute) and value.attr in {"BUY", "SELL"}:
        return value.attr
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        normalized = value.value.strip().upper()
        if normalized in {"BUY", "SELL"}:
            return normalized
    return "UNKNOWN"


def _metadata_from_call(node: ast.Call) -> tuple[str, tuple[str, ...], bool]:
    value = next((item.value for item in node.keywords if item.arg == "metadata"), None)
    if value is None:
        return "omitted", (), False
    if not isinstance(value, ast.Dict):
        return "dynamic_expression", (), True

    keys: list[str] = []
    dynamic = False
    for key in value.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            keys.append(key.value)
        else:
            dynamic = True
    return "literal_dict" if not dynamic else "literal_dict_with_expansion", tuple(sorted(set(keys))), dynamic


def _is_retired_grid_source(path: Path, root: Path) -> bool:
    """Keep code-present grid inventory out of actionable migration counts.

    Grid remains in the repository for explicit archived research, but its
    runtime policy is permanently retired.  This narrow filename check avoids
    importing runtime policy or executing any strategy while auditing source.
    """

    relative = path.relative_to(root).as_posix().lower()
    return relative in {"grid.py", "grid_async.py"}


def _safe_run_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    if not normalized:
        raise ValueError("run_id_required")
    return normalized[:120]
