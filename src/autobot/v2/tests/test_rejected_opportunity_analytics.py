import json

from autobot.v2.decision_journal import (
    DecisionJournal,
    REJECTION_REASON_ALLOCATION_ENVELOPE_BLOCKED,
    REJECTION_REASON_BLACK_SWAN_EMERGENCY_BLOCK,
    REJECTION_REASON_RANKING_BELOW_THRESHOLD,
    REJECTION_REASON_REPEATED_AUTO_ACTION_BLOCK,
    REJECTION_REASON_SCALABILITY_GUARD_BLOCK,
    REJECTION_REASON_SYMBOL_NOT_SELECTED,
    REJECTION_REASON_VALIDATION_GUARD_BLOCK,
    build_rejected_opportunity_report,
)


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_rejection_record_emission_and_schema_validity(tmp_path):
    out = tmp_path / "decision_journal.jsonl"
    journal = DecisionJournal(enabled=True, journal_path=str(out), runtime_context={"paper_trading": True})

    journal.log(
        decision_type="rejected_opportunity",
        source="validation_guard",
        symbols=["XXBTZEUR"],
        reasons=[REJECTION_REASON_VALIDATION_GUARD_BLOCK],
        context={"instance_id": "i1", "pass_score": 0.1},
    )
    journal.close()

    rows = _read_jsonl(out)
    assert len(rows) == 1
    row = rows[0]
    required = {"timestamp", "decision_type", "source", "symbols", "reasons", "context", "runtime"}
    assert required.issubset(set(row.keys()))
    assert row["decision_type"] == "rejected_opportunity"
    assert row["reasons"] == [REJECTION_REASON_VALIDATION_GUARD_BLOCK]


def test_rejection_reason_taxonomy_and_grouped_report_correctness(tmp_path):
    out = tmp_path / "decision_journal.jsonl"
    journal = DecisionJournal(enabled=True, journal_path=str(out), runtime_context={"paper_trading": True})

    taxonomy = [
        REJECTION_REASON_RANKING_BELOW_THRESHOLD,
        REJECTION_REASON_SCALABILITY_GUARD_BLOCK,
        REJECTION_REASON_VALIDATION_GUARD_BLOCK,
        REJECTION_REASON_REPEATED_AUTO_ACTION_BLOCK,
        REJECTION_REASON_BLACK_SWAN_EMERGENCY_BLOCK,
        REJECTION_REASON_ALLOCATION_ENVELOPE_BLOCKED,
        REJECTION_REASON_SYMBOL_NOT_SELECTED,
    ]
    for idx, reason in enumerate(taxonomy):
        journal.log(
            decision_type="rejected_opportunity",
            source="test",
            symbols=["XXBTZEUR" if idx % 2 == 0 else "XETHZEUR"],
            reasons=[reason],
            context={"idx": idx},
        )
    # extra duplicate for grouped count validation
    journal.log(
        decision_type="rejected_opportunity",
        source="test",
        symbols=["XXBTZEUR"],
        reasons=[REJECTION_REASON_VALIDATION_GUARD_BLOCK],
    )
    journal.close()

    report = build_rejected_opportunity_report(journal_path=str(out))
    assert report["total_rejections"] == len(taxonomy) + 1
    assert report["by_reason"][REJECTION_REASON_VALIDATION_GUARD_BLOCK] == 2
    assert report["by_symbol"]["XXBTZEUR"] >= 1
    assert report["reason_symbol"][f"{REJECTION_REASON_VALIDATION_GUARD_BLOCK}::XXBTZEUR"] == 2


def test_rejected_opportunity_report_safe_when_sparse_or_absent(tmp_path):
    missing = tmp_path / "missing.jsonl"
    report = build_rejected_opportunity_report(journal_path=str(missing), window_hours=24)
    assert report["window_hours"] == 24
    assert report["total_rejections"] == 0
    assert report["by_reason"] == {}
    assert report["by_symbol"] == {}
    assert report["records"] == []
