import json
import subprocess
import sys
from pathlib import Path


def _run_json_cli(repo_root: Path, args: list[str]) -> dict:
    proc = subprocess.run(
        [sys.executable, "tools/paper_ops.py", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_analytics_cli_commands_return_json_on_sparse_sources(tmp_path):
    repo_root = Path(__file__).resolve().parents[4]
    db_path = tmp_path / "missing_state.db"
    journal_path = tmp_path / "missing_journal.jsonl"

    rejected = _run_json_cli(
        repo_root,
        ["rejected-opportunities", "--journal-path", str(journal_path), "--format", "json"],
    )
    assert "generated_at" in rejected
    assert "total_rejections" in rejected
    assert "by_reason" in rejected

    pair_attr = _run_json_cli(
        repo_root,
        ["pair-attribution", "--db-path", str(db_path), "--format", "json"],
    )
    assert "generated_at" in pair_attr
    assert "totals" in pair_attr
    assert "pairs" in pair_attr

    consolidated = _run_json_cli(
        repo_root,
        [
            "profitability-review",
            "--db-path",
            str(db_path),
            "--journal-path",
            str(journal_path),
            "--format",
            "json",
        ],
    )
    assert "decision_journal_insights" in consolidated
    assert "pair_performance_attribution" in consolidated
    assert "rejected_opportunity_analytics" in consolidated

    autonomous = _run_json_cli(
        repo_root,
        [
            "autonomous-review",
            "--db-path",
            str(db_path),
            "--journal-path",
            str(journal_path),
            "--format",
            "json",
        ],
    )
    assert "system_health" in autonomous
    assert "top_pairs" in autonomous
    assert "top_rejection_reasons" in autonomous
