import json
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


def _run_cli(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/paper_ops.py", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_json_cli(repo_root: Path, args: list[str]) -> tuple[subprocess.CompletedProcess[str], dict]:
    proc = _run_cli(repo_root, args)
    payload = json.loads(proc.stdout)
    return proc, payload


def test_session_summary_missing_log_file_exits_nonzero(tmp_path):
    repo_root = Path(__file__).resolve().parents[4]
    missing_log = tmp_path / "missing.log"

    proc = _run_cli(repo_root, ["session-summary", "--log-file", str(missing_log), "--format", "json"])

    assert proc.returncode != 0
    assert "log file not found" in proc.stderr


def test_session_summary_empty_log_returns_stable_json_schema(tmp_path):
    repo_root = Path(__file__).resolve().parents[4]
    log_file = tmp_path / "empty.log"
    log_file.write_text("", encoding="utf-8")

    proc, payload = _run_json_cli(repo_root, ["session-summary", "--log-file", str(log_file), "--format", "json"])

    assert proc.returncode == 0, proc.stderr
    assert payload["window_hours"] == 24
    assert payload["log_file"] == str(log_file)
    assert payload["analysis_window"] == {"start_utc": None, "end_utc": None}
    assert payload["counts"] == {}
    assert payload["attestation"]["status"] == "unknown"
    assert payload["attestation"]["preflight_status"] == "unknown"
    assert payload["instances"] == {
        "created_mentions": 0,
        "unique_names": [],
        "unique_symbols": [],
    }
    assert payload["session_health"] == {
        "level": "stable",
        "warnings": 0,
        "errors": 0,
        "kill_switch_mentions": 0,
    }
    assert payload["top_warnings"] == []
    assert payload["top_errors"] == []
    assert payload["recent_warnings"] == []
    assert payload["recent_errors"] == []
    assert payload["status_artifact"] == {}
    assert set(payload["signals"].keys()) == {
        "ranking_clues",
        "opportunity_clues",
        "scaling_guard_clues",
        "allocation_clues",
        "universe_clues",
        "health_clues",
    }


def test_validate_missing_env_file_exits_nonzero(tmp_path):
    repo_root = Path(__file__).resolve().parents[4]
    missing_env = tmp_path / "missing.env"

    proc = _run_cli(repo_root, ["validate", "--env-file", str(missing_env)])

    assert proc.returncode != 0
    assert "env file not found" in proc.stderr
