import json
from pathlib import Path

from autobot.v2.decision_journal import DecisionJournal, journal_from_env


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_decision_journal_emits_major_records_when_enabled(tmp_path):
    out = tmp_path / "decision_journal.jsonl"
    journal = DecisionJournal(
        enabled=True,
        journal_path=str(out),
        runtime_context={"deployment_stage": "paper", "paper_trading": True},
    )

    wrote = journal.log(
        decision_type="activation_decision",
        source="instance_activation_manager",
        symbols=["XXBTZEUR", "XETHZEUR"],
        reasons=["promote_thresholds"],
        context={"target_tier": 2, "avg_rank_score": 78.5},
        session_id="paper-session-1",
    )
    journal.close()

    assert wrote is True
    rows = _read_jsonl(out)
    assert len(rows) == 1
    row = rows[0]
    assert row["decision_type"] == "activation_decision"
    assert row["source"] == "instance_activation_manager"
    assert row["symbols"] == ["XXBTZEUR", "XETHZEUR"]
    assert row["reasons"] == ["promote_thresholds"]
    assert row["context"]["target_tier"] == 2
    assert row["session_id"] == "paper-session-1"


def test_decision_journal_flag_off_is_noop_and_does_not_create_file(tmp_path):
    out = tmp_path / "disabled.jsonl"
    journal = DecisionJournal(enabled=False, journal_path=str(out))

    wrote = journal.log(
        decision_type="guard_decision",
        source="scalability_guard",
        reasons=["cpu_pressure"],
    )
    journal.close()

    assert wrote is False
    assert not out.exists()


def test_decision_journal_record_schema_validity(tmp_path):
    out = tmp_path / "schema.jsonl"
    journal = DecisionJournal(
        enabled=True,
        journal_path=str(out),
        runtime_context={"deployment_stage": "paper", "paper_trading": True, "pid": 42},
    )

    journal.log(
        decision_type="allocation_decision",
        source="portfolio_allocator",
        symbols=["XXBTZEUR"],
        reasons=["risk_cap_reached"],
        context={"total_allocated": 500.0, "risk_budget_remaining": 0.0},
    )
    journal.close()

    rows = _read_jsonl(out)
    assert len(rows) == 1
    row = rows[0]

    required = {"timestamp", "decision_type", "source", "symbols", "reasons", "context", "runtime"}
    assert required.issubset(set(row.keys()))
    assert isinstance(row["timestamp"], str)
    assert isinstance(row["symbols"], list)
    assert isinstance(row["reasons"], list)
    assert isinstance(row["context"], dict)
    assert isinstance(row["runtime"], dict)


def test_decision_journal_from_env_respects_flag_off(monkeypatch, tmp_path):
    out = tmp_path / "env_disabled.jsonl"
    monkeypatch.setenv("ENABLE_DECISION_JOURNAL", "false")
    monkeypatch.setenv("DECISION_JOURNAL_PATH", str(out))

    journal = journal_from_env()
    wrote = journal.log(
        decision_type="ranking_decision",
        source="pair_ranking_engine",
        symbols=["XXBTZEUR"],
        reasons=["ranking_refresh"],
    )
    journal.close()

    assert wrote is False
    assert not out.exists()
