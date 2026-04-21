import json

import autobot.v2.persistence as persistence_mod
from autobot.v2.consolidated_review import build_consolidated_profitability_review
from autobot.v2.decision_journal import DecisionJournal
from autobot.v2.persistence import StatePersistence


def _reset_thread_local_conn():
    conn = getattr(persistence_mod._local, "conn", None)
    if conn is not None:
        conn.close()
        delattr(persistence_mod._local, "conn")


def test_consolidated_review_generation_with_sparse_data(tmp_path):
    _reset_thread_local_conn()
    db = tmp_path / "state.db"
    journal = tmp_path / "journal.jsonl"

    report = build_consolidated_profitability_review(
        db_path=str(db),
        journal_path=str(journal),
        window_hours=24,
    )

    assert report["window_hours"] == 24
    assert report["decision_journal_insights"]["total_records"] == 0
    assert report["pair_performance_attribution"]["pair_count"] == 0
    assert report["rejected_opportunity_analytics"]["total_rejections"] == 0
    assert len(report["recommended_next_inspection_points"]) >= 1


def test_consolidated_review_schema_validity(tmp_path):
    _reset_thread_local_conn()
    db = tmp_path / "state.db"
    journal_path = tmp_path / "journal.jsonl"

    p = StatePersistence(db_path=str(db))
    p.append_trade_ledger(
        trade_id="t1",
        instance_id="i1",
        symbol="XXBTZEUR",
        side="sell",
        executed_price=100.0,
        volume=1.0,
        fees=0.4,
        realized_pnl=12.0,
        is_closing_leg=True,
    )

    j = DecisionJournal(enabled=True, journal_path=str(journal_path), runtime_context={"paper_trading": True})
    j.log(decision_type="activation_decision", source="instance_activation_manager", symbols=["XXBTZEUR"], reasons=["promote_thresholds"])
    j.log(decision_type="rejected_opportunity", source="validation_guard", symbols=["XXBTZEUR"], reasons=["validation_guard_block"])
    j.close()

    report = build_consolidated_profitability_review(
        db_path=str(db),
        journal_path=str(journal_path),
    )

    required = {
        "generated_at",
        "window_hours",
        "decision_journal_insights",
        "pair_performance_attribution",
        "rejected_opportunity_analytics",
        "highlights",
        "recommended_next_inspection_points",
    }
    assert required.issubset(set(report.keys()))
    assert report["decision_journal_insights"]["total_records"] >= 2
    assert report["pair_performance_attribution"]["pair_count"] >= 1
    assert isinstance(report["recommended_next_inspection_points"], list)


def test_consolidated_review_safe_when_one_source_absent(tmp_path):
    _reset_thread_local_conn()
    db = tmp_path / "state.db"
    p = StatePersistence(db_path=str(db))
    p.append_trade_ledger(
        trade_id="t1",
        instance_id="i1",
        symbol="XXBTZEUR",
        side="sell",
        executed_price=100.0,
        volume=1.0,
        fees=0.1,
        realized_pnl=4.0,
        is_closing_leg=True,
    )

    # Journal absent, pair attribution present
    report = build_consolidated_profitability_review(
        db_path=str(db),
        journal_path=str(tmp_path / "missing_journal.jsonl"),
    )
    assert report["decision_journal_insights"]["total_records"] == 0
    assert report["pair_performance_attribution"]["totals"]["total_trades"] == 1

    # quick JSON serializability safety check
    json.dumps(report)
