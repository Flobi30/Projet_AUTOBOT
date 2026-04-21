import json
import subprocess
import sys
from pathlib import Path

import autobot.v2.persistence as persistence_mod
from autobot.v2.autonomous_review import build_autonomous_review
from autobot.v2.decision_journal import DecisionJournal
from autobot.v2.persistence import StatePersistence
from tools.paper_ops import main as paper_ops_main


def _reset_thread_local_conn():
    conn = getattr(persistence_mod._local, "conn", None)
    if conn is not None:
        conn.close()
        delattr(persistence_mod._local, "conn")


def test_autonomous_review_sparse_data_behavior(tmp_path):
    _reset_thread_local_conn()
    db = tmp_path / "state.db"
    journal = tmp_path / "missing_journal.jsonl"

    report = build_autonomous_review(
        db_path=str(db),
        journal_path=str(journal),
        window_hours=24,
    )

    assert report["system_health"] in {"stable", "degraded", "critical"}
    assert report["recommended_action"] in {"hold", "expand", "reduce", "inspect"}
    assert report["source_snapshot"]["realized_trades"] == 0
    assert isinstance(report["focus_points"], list)


def test_autonomous_review_schema_validity(tmp_path):
    _reset_thread_local_conn()
    db = tmp_path / "state.db"
    journal = tmp_path / "journal.jsonl"

    p = StatePersistence(db_path=str(db))
    p.append_trade_ledger(
        trade_id="t1",
        instance_id="i1",
        symbol="XXBTZEUR",
        side="sell",
        executed_price=100.0,
        volume=1.0,
        fees=0.2,
        realized_pnl=10.0,
        is_closing_leg=True,
    )

    j = DecisionJournal(enabled=True, journal_path=str(journal), runtime_context={"paper_trading": True})
    j.log(decision_type="guard_decision", source="scalability_guard", reasons=["cpu_pressure"])
    j.log(decision_type="rejected_opportunity", source="validation_guard", symbols=["XXBTZEUR"], reasons=["validation_guard_block"])
    j.close()

    report = build_autonomous_review(db_path=str(db), journal_path=str(journal))

    required = {
        "generated_at",
        "window_hours",
        "system_health",
        "top_pairs",
        "bottom_pairs",
        "top_rejection_reasons",
        "rejection_reason_taxonomy",
        "scaling_summary",
        "allocation_hints",
        "recommended_action",
        "focus_points",
        "confidence",
        "source_snapshot",
    }
    assert required.issubset(set(report.keys()))


def test_autonomous_review_recommendation_output_correctness(tmp_path):
    _reset_thread_local_conn()
    db = tmp_path / "state.db"
    journal = tmp_path / "journal.jsonl"

    p = StatePersistence(db_path=str(db))
    p.append_trade_ledger(
        trade_id="neg-1",
        instance_id="i1",
        symbol="XXBTZEUR",
        side="sell",
        executed_price=100.0,
        volume=1.0,
        fees=0.2,
        realized_pnl=-25.0,
        is_closing_leg=True,
    )

    j = DecisionJournal(enabled=True, journal_path=str(journal), runtime_context={})
    j.log(decision_type="rejected_opportunity", source="validation_guard", symbols=["XXBTZEUR"], reasons=["validation_guard_block"])
    j.close()

    report = build_autonomous_review(db_path=str(db), journal_path=str(journal))
    assert report["recommended_action"] in {"reduce", "inspect"}
    assert report["system_health"] in {"degraded", "critical"}


def test_autonomous_review_no_crash_when_sources_missing(tmp_path):
    _reset_thread_local_conn()
    report = build_autonomous_review(
        db_path=str(tmp_path / "missing.db"),
        journal_path=str(tmp_path / "missing.jsonl"),
    )
    json.dumps(report)
    assert report["recommended_action"] in {"hold", "expand", "reduce", "inspect"}


def test_autonomous_review_cli_json_output(tmp_path, capsys):
    _reset_thread_local_conn()
    db = tmp_path / "state.db"
    journal = tmp_path / "journal.jsonl"
    j = DecisionJournal(enabled=True, journal_path=str(journal), runtime_context={})
    j.log(decision_type="rejected_opportunity", source="validation_guard", symbols=["XXBTZEUR"], reasons=["validation_guard_block"])
    j.close()

    exit_code = paper_ops_main(
        [
            "autonomous-review",
            "--db-path",
            str(db),
            "--journal-path",
            str(journal),
            "--format",
            "json",
        ]
    )
    assert exit_code == 0

    payload = capsys.readouterr().out.strip()
    parsed = json.loads(payload)
    assert isinstance(parsed, dict)
    assert "system_health" in parsed
    assert "top_pairs" in parsed
    assert "bottom_pairs" in parsed
    assert "top_rejection_reasons" in parsed
    assert "scaling_summary" in parsed
    assert "allocation_hints" in parsed
    assert "recommended_action" in parsed
    assert "focus_points" in parsed
    assert "confidence" in parsed


def test_autonomous_review_cli_script_works_without_pythonpath(tmp_path):
    _reset_thread_local_conn()
    repo_root = Path(__file__).resolve().parents[4]
    db = tmp_path / "state.db"
    journal = tmp_path / "journal.jsonl"

    proc = subprocess.run(
        [
            sys.executable,
            "tools/paper_ops.py",
            "autonomous-review",
            "--db-path",
            str(db),
            "--journal-path",
            str(journal),
            "--format",
            "json",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    parsed = json.loads(proc.stdout)
    assert isinstance(parsed, dict)
    assert "system_health" in parsed
