from __future__ import annotations

import csv
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research.alpha_hypothesis_scheduler import (
    AlphaResearchMemory,
    AlphaSchedulerConfig,
    AlphaSchedulerError,
    ResearchMemoryRecord,
    backfill_alpha_research_memory,
    build_alpha_hypothesis_scheduler_report,
    load_alpha_knowledge_base,
    load_alpha_research_memory,
    load_strategy_templates,
    record_alpha_runner_trial,
    scan_data_readiness,
)
from autobot.v2.research.alpha_hypothesis_runner import AlphaHypothesisRunnerConfig, build_alpha_hypothesis_runner_report
from autobot.v2.research.research_memory_store import ResearchMemoryStore
from autobot.v2.strategy_runtime_policy import is_runtime_engine_retired


pytestmark = pytest.mark.unit


def test_alpha_knowledge_base_and_templates_are_research_only():
    knowledge = load_alpha_knowledge_base("docs/research/alpha_knowledge_base.json")
    templates = load_strategy_templates("docs/research/strategy_templates.json")

    assert len(knowledge["families"]) >= 13
    assert len(templates["templates"]) >= 7
    assert knowledge["free_code_generation_allowed"] is False
    assert templates["free_code_generation_allowed"] is False
    assert all(item.get("paper_capital_allowed") is not True for item in templates["templates"])
    assert all(item.get("live_allowed") is not True for item in templates["templates"])
    assert all(item["max_variants"] <= 5 for item in templates["templates"])
    assert "grid" not in {item["alpha_family_id"] for item in knowledge["families"]}
    assert is_runtime_engine_retired("grid") is True


def test_knowledge_base_rejects_free_code_generation(tmp_path):
    payload = json.loads(Path("docs/research/alpha_knowledge_base.json").read_text(encoding="utf-8"))
    payload["free_code_generation_allowed"] = True
    path = tmp_path / "kb.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AlphaSchedulerError, match="free code"):
        load_alpha_knowledge_base(path)


def test_research_memory_counts_each_variant(tmp_path):
    memory = AlphaResearchMemory(tmp_path / "memory.json", ())
    first = _record("r1", variant_count=3)
    second = _record("r2", variant_count=2)

    updated = memory.add_record(first).add_record(second)

    assert updated.trial_count_by_family()["volatility_breakout"] == 5
    assert updated.trial_count_by_template()["breakout_after_compression"] == 5
    assert updated.records[-1].trial_count_for_family == 5
    assert updated.records[-1].trial_count_for_template == 5


def test_memory_rejects_paper_or_live_enabled_record(tmp_path):
    payload = {
        "schema_version": 1,
        "research_only": True,
        "paper_capital_allowed": False,
        "live_allowed": False,
        "free_code_generation_allowed": False,
        "records": [
            {
                **_record("bad").to_dict(),
                "paper_capital_allowed": True,
            }
        ],
    }
    path = tmp_path / "memory.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AlphaSchedulerError, match="paper/live/promotion"):
        load_alpha_research_memory(path)


def test_sqlite_memory_is_append_only_idempotent_and_keeps_latest_record(tmp_path):
    path = tmp_path / "memory.sqlite3"
    store = ResearchMemoryStore(path)
    first = _record("sqlite-run", variant_count=1).to_dict()
    changed = {**first, "metrics": {"net_pnl_eur": 3.0}}

    assert store.append(first) is True
    assert store.append(first) is False
    assert store.append(changed) is True
    assert store.event_count() == 2
    loaded = load_alpha_research_memory(path)

    assert len(loaded.records) == 1
    assert loaded.records[0].metrics["net_pnl_eur"] == 3.0
    assert loaded.records[0].paper_capital_allowed is False

    export_path = store.export_latest(tmp_path / "review" / "memory.json")
    exported = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported["source_event_count"] == 2
    assert exported["paper_capital_allowed"] is False
    assert len(exported["records"]) == 1


def test_scheduler_refuses_rejected_current_config_and_selects_next_runnable(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    memory_path = tmp_path / "memory.json"
    AlphaResearchMemory(memory_path, ()).add_record(
        _record("p18d", final_status="REJECTED", variant_count=5)
    ).write(memory_path)

    report = build_alpha_hypothesis_scheduler_report(
        AlphaSchedulerConfig(
            run_id="pytest_scheduler",
            state_db=tmp_path / "state.db",
            data_paths=(data_dir,),
            memory_path=memory_path,
            max_variants=5,
            max_symbols=6,
            max_runtime_seconds=300,
        )
    )

    by_template = {item.template_id: item for item in report.candidates}
    assert by_template["breakout_after_compression"].status == "REJECTED_CURRENT_CONFIG"
    assert by_template["funding_extreme_reversion"].status == "DATA_MISSING"
    assert by_template["liquidation_recovery"].status == "DATA_MISSING"
    assert report.selected is not None
    assert report.selected.status == "RUNNABLE_SMOKE"
    assert report.selected.template_id in {"leader_laggard_momentum", "relative_strength_rotation", "regime_filtered_trend"}
    assert "--mode smoke" in str(report.next_runner_command)
    assert report.paper_capital_allowed is False
    assert report.live_allowed is False
    assert report.promotable is False


def test_scheduler_marks_generic_cross_sectional_adapter_ready_when_data_exists(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    report = build_alpha_hypothesis_scheduler_report(
        AlphaSchedulerConfig(
            run_id="pytest_adapter_missing",
            state_db=None,
            data_paths=(data_dir,),
            memory_path=tmp_path / "empty_memory.json",
        )
    )

    candidates = {item.template_id: item for item in report.candidates}
    assert candidates["leader_laggard_momentum"].status == "RUNNABLE_SMOKE"
    assert candidates["leader_laggard_momentum"].adapter_ready is True
    assert "adapter_missing" not in candidates["leader_laggard_momentum"].blockers
    assert "--template-id leader_laggard_momentum" in str(candidates["leader_laggard_momentum"].recommended_command)


def test_cross_sectional_template_rejection_is_recorded_without_blocking_family(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    memory_path = tmp_path / "memory.json"
    report = build_alpha_hypothesis_runner_report(
        AlphaHypothesisRunnerConfig(
            run_id="pytest_cross_reject",
            hypothesis_id="cross_momentum",
            mode="smoke",
            data_paths=(data_dir,),
            symbols=("BCHEUR", "ADAEUR"),
            max_variants=1,
            max_symbols=2,
            template_id="leader_laggard_momentum",
        ),
        commit="test",
    )

    record = record_alpha_runner_trial(
        report,
        memory_path=memory_path,
        template_id="leader_laggard_momentum",
        alpha_family_id="cross_sectional_momentum",
    )
    memory = load_alpha_research_memory(memory_path)

    assert record.adapter_id == "generic_cross_sectional_ohlcv_adapter"
    assert record.mode_used == "leader_laggard_momentum"
    if record.final_status in {"REJECT_FAST", "DATA_MISSING", "REJECTED"}:
        assert "cross_momentum" not in memory.rejected_hypotheses()
        assert "cross_momentum__leader_laggard_momentum" in memory.rejected_hypotheses()


def test_scheduler_cli_is_registered():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "alpha-hypothesis-scheduler",
            "--state-db",
            "data/autobot_state.db",
            "--data-paths",
            "data/research/daily/ohlcv",
        ]
    )

    assert args.command == "alpha-hypothesis-scheduler"
    assert args.max_variants == 5
    assert args.max_symbols == 6


def test_memory_backfill_is_idempotent_and_adds_historical_records(tmp_path):
    memory_path = tmp_path / "memory.json"

    first = backfill_alpha_research_memory(memory_path=memory_path)
    second = backfill_alpha_research_memory(memory_path=memory_path)
    memory = load_alpha_research_memory(memory_path)
    run_ids = [record.run_id for record in memory.records]

    assert first.added_count >= 5
    assert second.added_count == 0
    assert len(run_ids) == len(set(run_ids))
    assert "p17_high_conviction_history_20260709" in run_ids
    assert "relative_value_20260622" in run_ids
    assert all(record.paper_capital_allowed is False for record in memory.records)
    assert all(record.live_allowed is False for record in memory.records)
    assert all(record.promotable is False for record in memory.records)


def test_rejected_long_trend_and_volatility_receive_zero_priority_after_backfill(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    memory_path = tmp_path / "memory.json"
    backfill_alpha_research_memory(memory_path=memory_path)

    report = build_alpha_hypothesis_scheduler_report(
        AlphaSchedulerConfig(
            run_id="pytest_backfilled_scheduler",
            state_db=tmp_path / "state.db",
            data_paths=(data_dir,),
            memory_path=memory_path,
        )
    )
    by_template = {item.template_id: item for item in report.candidates}

    assert by_template["regime_filtered_trend"].status == "REJECTED_CURRENT_CONFIG"
    assert by_template["regime_filtered_trend"].priority_score == 0
    assert by_template["breakout_after_compression"].status == "REJECTED_CURRENT_CONFIG"
    assert by_template["breakout_after_compression"].priority_score == 0


def test_adapter_backlog_no_longer_contains_generic_cross_sectional_adapter(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    memory_path = tmp_path / "memory.json"
    backfill_alpha_research_memory(memory_path=memory_path)

    report = build_alpha_hypothesis_scheduler_report(
        AlphaSchedulerConfig(
            run_id="pytest_adapter_backlog",
            state_db=None,
            data_paths=(data_dir,),
            memory_path=memory_path,
        )
    )

    adapter_ids = {item.adapter_id for item in report.adapter_backlog}
    assert "generic_cross_sectional_ohlcv_adapter" not in adapter_ids
    assert {item.template_id for item in report.adapter_backlog}.issuperset(
        {"funding_extreme_reversion"}
    )
    assert all(item.template_id not in {"leader_laggard_momentum", "relative_strength_rotation"} for item in report.adapter_backlog)


def test_backfilled_grid_remains_no_go_and_rejected(tmp_path):
    memory_path = tmp_path / "memory.json"
    backfill_alpha_research_memory(memory_path=memory_path)
    memory = load_alpha_research_memory(memory_path)
    grid_record = next(record for record in memory.records if record.hypothesis_id == "grid")

    assert "grid" in memory.rejected_hypotheses()
    assert grid_record.final_status == "RETIRED_FROM_EXECUTION"
    assert grid_record.paper_capital_allowed is False
    assert grid_record.live_allowed is False


def test_data_readiness_detects_ohlcv_symbols_and_timeframes(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    readiness = scan_data_readiness((data_dir,))

    assert readiness.has_spot_ohlcv is True
    assert readiness.has_multi_symbol_ohlcv is True
    assert readiness.has_5m is True
    assert readiness.has_15m is True
    assert readiness.has_1h is True
    assert set(readiness.symbols) == {"ADAEUR", "BCHEUR"}


def test_scheduler_explains_capability_blockers_without_relaunching_rejected(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    memory_path = tmp_path / "memory.json"
    AlphaResearchMemory(memory_path, ()).add_record(
        _record("p18d", final_status="REJECTED", variant_count=5)
    ).write(memory_path)

    report = build_alpha_hypothesis_scheduler_report(
        AlphaSchedulerConfig(
            run_id="pytest_capability_scheduler",
            state_db=None,
            data_paths=(data_dir,),
            memory_path=memory_path,
        )
    )

    capability_ids = {item["capability_id"] for item in report.data_capabilities["capabilities"]}
    assert "funding_rates" in capability_ids
    assert "scheduler_data_state" in report.data_capabilities
    assert report.data_capabilities["scheduler_data_state"]["funding_data_ready"] is False
    assert report.data_capabilities["scheduler_data_state"]["liquidation_data_ready"] is False
    assert report.data_capabilities["alpha_family_status"]["funding_basis"]["status"] == "DATA_MISSING"
    assert "funding_rates_missing" in report.data_capabilities["alpha_family_status"]["funding_basis"]["blockers"]
    assert report.data_capabilities["rejected_family_status"]["volatility_breakout"]["retest_allowed"] is False
    by_template = {item.template_id: item for item in report.candidates}
    assert by_template["breakout_after_compression"].status == "REJECTED_CURRENT_CONFIG"


def _record(
    run_id: str,
    *,
    final_status: str = "REJECTED",
    variant_count: int = 1,
) -> ResearchMemoryRecord:
    return ResearchMemoryRecord(
        run_id=run_id,
        hypothesis_id="volatility_breakout",
        alpha_family_id="volatility_breakout",
        template_id="breakout_after_compression",
        created_at="2026-07-09T00:00:00+00:00",
        data_snapshot={"rows": 100},
        parameters_tested={"mode": "walk_forward"},
        variant_count=variant_count,
        symbols_tested=("BCHEUR",),
        gate_results=({"gate": "WALK_FORWARD", "status": "REJECT", "passed": False},),
        final_status=final_status,
        rejection_reasons=("majority_folds_negative",),
        trial_count_for_family=variant_count,
        trial_count_for_template=variant_count,
        related_rejected_hypotheses=("volatility_breakout",),
        do_not_rerun_until=None,
        requires_new_data_before_rerun=True,
    )


def _write_ohlcv(tmp_path: Path) -> Path:
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for symbol in ("BCHEUR", "ADAEUR"):
        _write_rows(data_dir / f"{symbol}_1h.csv", symbol, "1h", start, 20, timedelta(hours=1))
        _write_rows(data_dir / f"{symbol}_15m.csv", symbol, "15m", start, 80, timedelta(minutes=15))
        _write_rows(data_dir / f"{symbol}_5m.csv", symbol, "5m", start, 240, timedelta(minutes=5))
    return data_dir


def _write_rows(path: Path, symbol: str, timeframe: str, start: datetime, count: int, step: timedelta) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume", "symbol", "timeframe"],
        )
        writer.writeheader()
        for index in range(count):
            price = 100 + index * 0.1
            writer.writerow(
                {
                    "timestamp": (start + index * step).isoformat(),
                    "open": price,
                    "high": price * 1.01,
                    "low": price * 0.99,
                    "close": price * 1.001,
                    "volume": 1000,
                    "symbol": symbol,
                    "timeframe": timeframe,
                }
            )
