import json

import autobot.v2.persistence as persistence_mod
from autobot.v2.autonomous_review import build_autonomous_review
from autobot.v2.decision_journal import DecisionJournal
from autobot.v2.persistence import StatePersistence


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

    assert report["global_system_health"] in {"stable", "degraded", "critical"}
    assert report["recommended_action"] in {"hold", "expand", "reduce", "inspect"}
    assert report["source_snapshot"]["realized_trades"] == 0
    assert isinstance(report["recommended_focus_points"], list)


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
        "global_system_health",
        "top_performing_pairs",
        "underperforming_pairs",
        "dominant_rejection_reasons",
        "scaling_guard_behavior_summary",
        "allocation_behavior_clues",
        "recommended_action",
        "recommended_focus_points",
        "confidence_level",
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
    assert report["global_system_health"] in {"degraded", "critical"}


def test_autonomous_review_no_crash_when_sources_missing(tmp_path):
    _reset_thread_local_conn()
    report = build_autonomous_review(
        db_path=str(tmp_path / "missing.db"),
        journal_path=str(tmp_path / "missing.jsonl"),
    )
    json.dumps(report)
    assert report["recommended_action"] in {"hold", "expand", "reduce", "inspect"}
