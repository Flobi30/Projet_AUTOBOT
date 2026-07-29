"""Static, no-network safety audit for AUTOBOT public data collectors.

The research collectors are allowed to contact documented public market-data
endpoints, but they must never inherit an order path, a private Kraken client
or a private credential reference.  This module reads collector source only;
it does not import collectors, read runtime state or create any network client.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


PUBLIC_COLLECTOR_MODULES = (
    "historical_data_collector",
    "spread_depth_recorder",
    "forward_microstructure_collection",
    "kraken_futures_derivatives_collector",
)

_FORBIDDEN_IMPORT_PREFIXES = (
    "krakenex",
    "order_executor",
    "order_executor_async",
    "order_router",
    "paper_trading",
    "execution_authorization",
    "main_async",
    "orchestrator",
    "orchestrator_async",
    "signal_handler_async",
)
_FORBIDDEN_REFERENCES = frozenset(
    {
        "KRAKEN_API_KEY",
        "KRAKEN_API_SECRET",
        "query_private",
    }
)


class PublicCollectorBoundaryError(RuntimeError):
    """Raised when public collector source crosses a private boundary."""


@dataclass(frozen=True)
class PublicCollectorBoundaryFinding:
    module: str
    line: int
    kind: str
    value: str

    def to_dict(self) -> dict[str, object]:
        return {
            "module": self.module,
            "line": self.line,
            "kind": self.kind,
            "value": self.value,
        }


@dataclass(frozen=True)
class PublicCollectorBoundaryReport:
    modules: tuple[str, ...]
    findings: tuple[PublicCollectorBoundaryFinding, ...]

    @property
    def passed(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, object]:
        return {
            "audit": "public_collector_boundary",
            "network_access": "not_used",
            "runtime_state_access": "not_used",
            "modules": list(self.modules),
            "passed": self.passed,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def _module_source_paths(
    module_names: Iterable[str] | None = None,
) -> dict[str, Path]:
    names = tuple(module_names or PUBLIC_COLLECTOR_MODULES)
    unknown = sorted(set(names) - set(PUBLIC_COLLECTOR_MODULES))
    if unknown:
        raise PublicCollectorBoundaryError(
            "unknown public collector module(s): " + ", ".join(unknown)
        )
    source_root = Path(__file__).resolve().parent
    return {name: source_root / f"{name}.py" for name in names}


def _is_forbidden_import(module_name: str) -> bool:
    normalized = module_name.lstrip(".")
    leaf = normalized.rsplit(".", 1)[-1]
    return any(
        normalized == prefix
        or normalized.endswith(f".{prefix}")
        or leaf == prefix
        for prefix in _FORBIDDEN_IMPORT_PREFIXES
    )


def audit_public_collector_sources(
    source_paths: Mapping[str, Path],
) -> PublicCollectorBoundaryReport:
    """Inspect supplied source files without importing or executing them."""
    findings: list[PublicCollectorBoundaryFinding] = []
    modules = tuple(source_paths)
    for module, source_path in source_paths.items():
        try:
            source = source_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(source_path))
        except (OSError, SyntaxError) as exc:
            raise PublicCollectorBoundaryError(
                f"cannot inspect public collector {module}: {exc}"
            ) from exc

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_forbidden_import(alias.name):
                        findings.append(
                            PublicCollectorBoundaryFinding(
                                module=module,
                                line=node.lineno,
                                kind="forbidden_import",
                                value=alias.name,
                            )
                        )
            elif isinstance(node, ast.ImportFrom):
                imported_module = node.module or ""
                if _is_forbidden_import(imported_module):
                    findings.append(
                        PublicCollectorBoundaryFinding(
                            module=module,
                            line=node.lineno,
                            kind="forbidden_import",
                            value=imported_module,
                        )
                    )
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in _FORBIDDEN_REFERENCES:
                    findings.append(
                        PublicCollectorBoundaryFinding(
                            module=module,
                            line=node.lineno,
                            kind="forbidden_reference",
                            value=node.value,
                        )
                    )
            elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_REFERENCES:
                findings.append(
                    PublicCollectorBoundaryFinding(
                        module=module,
                        line=node.lineno,
                        kind="forbidden_reference",
                        value=node.attr,
                    )
                )

    return PublicCollectorBoundaryReport(
        modules=modules,
        findings=tuple(sorted(findings, key=lambda item: (item.module, item.line, item.kind, item.value))),
    )


def audit_public_collector_boundary(
    module_names: Iterable[str] | None = None,
) -> PublicCollectorBoundaryReport:
    """Audit one or more known public collector modules from this source tree."""
    return audit_public_collector_sources(_module_source_paths(module_names))


def assert_public_collector_boundary(
    module_names: Iterable[str] | None = None,
) -> PublicCollectorBoundaryReport:
    """Fail closed before a public collector can run with unsafe source code."""
    report = audit_public_collector_boundary(module_names)
    if not report.passed:
        details = "; ".join(
            f"{finding.module}:{finding.line}:{finding.kind}:{finding.value}"
            for finding in report.findings
        )
        raise PublicCollectorBoundaryError(
            "public collector boundary violation: " + details
        )
    return report
