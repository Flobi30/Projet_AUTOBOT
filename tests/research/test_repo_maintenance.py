from pathlib import Path

import pytest

from autobot.v2.research.repo_maintenance import (
    build_import_graph,
    cleanup_safe_candidates,
    discover_safe_cleanup_candidates,
    is_critical_path,
)


pytestmark = pytest.mark.unit


def test_cleanup_candidates_do_not_include_critical_databases(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "src" / "pkg" / "__pycache__").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__pycache__" / "mod.cpython-311.pyc").write_bytes(b"cache")
    (tmp_path / ".pytest_cache").mkdir()
    (tmp_path / "data" / "autobot_state.db").write_bytes(b"db")
    (tmp_path / "data" / "paper_trades.db").write_bytes(b"db")

    candidates = discover_safe_cleanup_candidates(tmp_path)
    candidate_paths = {item.path for item in candidates}

    assert tmp_path / "data" / "autobot_state.db" not in candidate_paths
    assert tmp_path / "data" / "paper_trades.db" not in candidate_paths
    assert any(item.path.name == "__pycache__" for item in candidates)
    assert any(item.path.name == ".pytest_cache" for item in candidates)


def test_cleanup_manifest_records_deletions_without_reports_or_db(tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "keep.md").write_text("keep", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "autobot_state.db").write_bytes(b"db")
    (tmp_path / "pkg" / "__pycache__").mkdir(parents=True)
    (tmp_path / "pkg" / "__pycache__" / "x.pyc").write_bytes(b"cache")
    manifest_path = tmp_path / "cleanup_manifest.json"

    manifest = cleanup_safe_candidates(tmp_path, manifest_path=manifest_path, dry_run=False)

    assert manifest["safety"]["databases_deleted"] is False
    assert manifest["safety"]["reports_deleted"] is False
    assert (tmp_path / "reports" / "keep.md").exists()
    assert (tmp_path / "data" / "autobot_state.db").exists()
    assert not (tmp_path / "pkg" / "__pycache__").exists()
    assert manifest_path.exists()


def test_is_critical_path_blocks_known_db_names():
    assert is_critical_path(Path("data/autobot_state.db"))
    assert is_critical_path(Path("data/paper_trades.db"))
    assert is_critical_path(Path("data/autobot_state.db-wal"))


def test_build_import_graph_uses_ast_and_optional_networkx(tmp_path):
    pkg = tmp_path / "autobot" / "v2"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "a.py").write_text("import autobot.v2.b\n", encoding="utf-8")
    (pkg / "b.py").write_text("from autobot.v2 import a\n", encoding="utf-8")

    graph = build_import_graph(tmp_path)

    assert "autobot.v2.a" in graph["nodes"]
    assert ["autobot.v2.a", "autobot.v2.b"] in graph["edges"]
    assert "networkx_available" in graph
