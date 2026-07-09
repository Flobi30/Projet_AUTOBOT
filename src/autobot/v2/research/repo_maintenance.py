"""Repository audit and safe cleanup helpers for research maintenance.

The cleanup helpers intentionally target only generated caches and explicit
temporary artifacts. They do not delete databases, reports, backups, configs,
or secrets.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


CRITICAL_NAMES = {
    ".env",
    ".env.local",
    "autobot_state.db",
    "paper_trades.db",
    "global_kill_switch.db",
    "nonce_state.db",
    "setup_shadow_lab.db",
}
PROTECTED_PARTS = {"data", "reports", "backups", "config", ".git"}
CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
CACHE_FILE_SUFFIXES = {".pyc", ".pyo"}


@dataclass(frozen=True)
class CleanupCandidate:
    path: Path
    size_bytes: int
    reason: str

    def to_manifest_entry(self, root: Path) -> dict[str, object]:
        return {
            "path": _rel(self.path, root),
            "size_bytes": self.size_bytes,
            "reason": self.reason,
        }


def is_critical_path(path: Path) -> bool:
    parts = set(path.parts)
    if path.name in CRITICAL_NAMES:
        return True
    if path.suffix == ".db" or path.name.endswith((".db-shm", ".db-wal")):
        return True
    if "data" in parts and path.suffix in {".db", ".sqlite", ".sqlite3"}:
        return True
    return False


def path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def discover_safe_cleanup_candidates(root: Path) -> list[CleanupCandidate]:
    root = root.resolve()
    candidates: dict[Path, CleanupCandidate] = {}
    for path in root.rglob("*"):
        if not path.exists():
            continue
        if is_critical_path(path):
            continue
        rel_parts = set(path.relative_to(root).parts)
        if rel_parts & {"data", "reports", "backups", ".git"}:
            continue
        if path.is_dir() and path.name in CACHE_DIR_NAMES:
            candidates[path] = CleanupCandidate(path, path_size(path), f"generated_cache_dir:{path.name}")
        elif path.is_file() and path.suffix in CACHE_FILE_SUFFIXES:
            candidates[path] = CleanupCandidate(path, path.stat().st_size, f"generated_python_cache:{path.suffix}")
        elif path.is_file() and path.suffix == ".log" and path.name.endswith(".log"):
            candidates[path] = CleanupCandidate(path, path.stat().st_size, "generated_log_file")
    return sorted(candidates.values(), key=lambda item: str(item.path))


def cleanup_safe_candidates(
    root: Path,
    *,
    manifest_path: Path,
    dry_run: bool = False,
) -> dict[str, object]:
    root = root.resolve()
    candidates = discover_safe_cleanup_candidates(root)
    deleted: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for candidate in candidates:
        if is_critical_path(candidate.path):
            skipped.append({**candidate.to_manifest_entry(root), "reason": "critical_path_skipped"})
            continue
        entry = candidate.to_manifest_entry(root)
        if not dry_run:
            if candidate.path.is_dir():
                shutil.rmtree(candidate.path)
            elif candidate.path.exists():
                candidate.path.unlink()
        deleted.append(entry)
    manifest = {
        "schema_version": 1,
        "mode": "dry_run" if dry_run else "deleted",
        "root": str(root),
        "deleted_count": len(deleted) if not dry_run else 0,
        "candidate_count": len(candidates),
        "deleted_size_bytes": sum(int(item["size_bytes"]) for item in deleted),
        "deleted": deleted,
        "skipped": skipped,
        "safety": {
            "databases_deleted": False,
            "reports_deleted": False,
            "backups_deleted": False,
            "secrets_deleted": False,
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def build_import_graph(root: Path, *, package_prefix: str = "autobot") -> dict[str, object]:
    root = root.resolve()
    nodes: set[str] = set()
    edges: set[tuple[str, str]] = set()
    parse_errors: list[dict[str, str]] = []
    for file_path in root.rglob("*.py"):
        if "__pycache__" in file_path.parts:
            continue
        module = _module_name(root, file_path)
        nodes.add(module)
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError as exc:
            parse_errors.append({"path": _rel(file_path, root), "error": str(exc)})
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(package_prefix):
                        edges.add((module, alias.name))
            elif isinstance(node, ast.ImportFrom):
                target = _resolve_import_from(module, node)
                if target and target.startswith(package_prefix):
                    edges.add((module, target))
    graph = {"nodes": sorted(nodes), "edges": sorted([list(edge) for edge in edges]), "parse_errors": parse_errors}
    try:
        import networkx as nx  # type: ignore

        nx_graph = nx.DiGraph()
        nx_graph.add_nodes_from(graph["nodes"])
        nx_graph.add_edges_from((src, dst) for src, dst in edges)
        graph["networkx_available"] = True
        graph["strongly_connected_components"] = [sorted(item) for item in nx.strongly_connected_components(nx_graph) if len(item) > 1]
    except Exception:
        graph["networkx_available"] = False
        graph["strongly_connected_components"] = []
    return graph


def _module_name(root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def _resolve_import_from(module: str, node: ast.ImportFrom) -> str | None:
    if node.module is None:
        return None
    if node.level == 0:
        return node.module
    parts = module.split(".")
    base = parts[: max(0, len(parts) - node.level)]
    return ".".join([*base, node.module])


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()

