from __future__ import annotations

import ast
import csv
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research import bounded_research_coordinator as coordinator
from autobot.v2.research.alpha_hypothesis_scheduler import (
    AlphaResearchMemory,
    AlphaSchedulerConfig,
    ResearchMemoryRecord,
)
from autobot.v2.research.bounded_research_coordinator import (
    BoundedResearchCoordinatorConfig,
    run_bounded_research_coordinator,
)
from autobot.v2.research.experiment_registry import ExperimentRegistry
from autobot.v2.research.research_memory_store import ResearchMemoryStore


pytestmark = pytest.mark.unit


def test_coordinator_runs_one_allowlisted_smoke_and_deduplicates_terminal_fingerprint(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    feature_manifest = _feature_manifest(tmp_path)
    memory_path = tmp_path / "memory.sqlite3"
    _reject_long_trend(memory_path)
    config = _config(tmp_path, data_dir, feature_manifest, memory_path)

    first = run_bounded_research_coordinator(config)

    assert first.decision == "RESEARCH_SMOKE_COMPLETED"
    assert first.selected_hypothesis_id == "cross_momentum"
    assert first.selected_template_id in {"leader_laggard_momentum", "relative_strength_rotation"}
    assert first.runner_report is not None
    assert first.runner_report.mode == "smoke"
    assert first.runner_report.paper_capital_allowed is False
    assert first.runner_report.live_allowed is False
    assert first.runner_report.promotable is False
    assert first.experiment_registry_state is not None
    assert first.experiment_registry_state["trial_count"] > 0
    assert ResearchMemoryStore(memory_path).event_count() >= 2

    second = run_bounded_research_coordinator(config)

    assert second.decision == "SKIPPED_FEATURE_SNAPSHOT_ALREADY_CLAIMED"
    assert second.runner_report is None
    assert "feature_snapshot_already_has_bounded_research_attempt" in second.reasons


def test_coordinator_fails_closed_when_scheduler_selects_nothing(tmp_path, monkeypatch):
    config = _config(tmp_path, tmp_path / "missing-data", tmp_path / "missing-manifest.json", tmp_path / "memory.sqlite3")
    base = coordinator.build_alpha_hypothesis_scheduler_report(config.scheduler)
    monkeypatch.setattr(coordinator, "build_alpha_hypothesis_scheduler_report", lambda _config: replace(base, selected=None))

    report = run_bounded_research_coordinator(config)

    assert report.decision == "NO_RUNNABLE_CANDIDATE"
    assert report.runner_report is None
    assert not config.experiment_registry_path.exists()
    assert not config.memory_path.exists()


def test_coordinator_refuses_feature_snapshot_without_runtime_parity(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    feature_manifest = _feature_manifest(tmp_path, runtime_parity_proven=False)
    memory_path = tmp_path / "memory.sqlite3"
    _reject_long_trend(memory_path)

    report = run_bounded_research_coordinator(_config(tmp_path, data_dir, feature_manifest, memory_path))

    assert report.decision == "BLOCKED_INVALID_PROVENANCE"
    assert "runtime parity must be proven" in report.reasons[0]
    assert not (tmp_path / "registry.sqlite3").exists()


def test_coordinator_records_a_fail_closed_report_when_runner_raises(tmp_path, monkeypatch):
    data_dir = _write_ohlcv(tmp_path)
    feature_manifest = _feature_manifest(tmp_path)
    memory_path = tmp_path / "memory.sqlite3"
    _reject_long_trend(memory_path)
    monkeypatch.setattr(
        coordinator,
        "build_alpha_hypothesis_runner_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("fixture_runner_failure")),
    )

    report = run_bounded_research_coordinator(_config(tmp_path, data_dir, feature_manifest, memory_path))

    assert report.decision == "RESEARCH_RUNNER_ERROR_LOCKED"
    assert "RuntimeError:fixture_runner_failure" in report.reasons[0]
    assert report.runner_report is None
    assert report.experiment_registry_state is not None


def test_coordinator_cli_is_registered_and_has_no_execution_switch():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "bounded-research-coordinator",
            "--run-id",
            "pytest",
            "--data-paths",
            "data/research/canonical/ohlcv",
            "--feature-snapshot-manifest",
            "data/research/manifests/features.json",
        ]
    )

    assert args.command == "bounded-research-coordinator"
    assert args.max_variants == 3
    assert args.max_symbols == 6
    assert args.max_runtime_seconds == 120
    assert not hasattr(args, "enable_live")
    assert not hasattr(args, "enable_paper")


def test_coordinator_has_no_runtime_order_imports():
    root = Path(__file__).resolve().parents[2]
    module = root / "src/autobot/v2/research/bounded_research_coordinator.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )

    forbidden = {
        "autobot.v2.order_router",
        "autobot.v2.signal_handler_async",
        "autobot.v2.kraken_client",
        "autobot.v2.paper_trading",
    }
    assert imports.isdisjoint(forbidden)


def _config(
    tmp_path: Path,
    data_dir: Path,
    feature_manifest: Path,
    memory_path: Path,
) -> BoundedResearchCoordinatorConfig:
    return BoundedResearchCoordinatorConfig(
        run_id="pytest_bounded",
        scheduler=AlphaSchedulerConfig(
            state_db=None,
            data_paths=(data_dir,),
            memory_path=memory_path,
            output_dir=tmp_path / "scheduler",
            run_id="pytest_bounded_scheduler",
            max_variants=1,
            max_symbols=2,
            max_runtime_seconds=30,
        ),
        feature_snapshot_manifest=feature_manifest,
        code_commit="test-commit",
        output_dir=tmp_path / "reports",
        memory_path=memory_path,
        experiment_registry_path=tmp_path / "registry.sqlite3",
    )


def _reject_long_trend(memory_path: Path) -> None:
    record = ResearchMemoryRecord(
        run_id="historical_long_trend_reject",
        hypothesis_id="long_trend",
        alpha_family_id="trend_momentum",
        template_id="regime_filtered_trend",
        created_at="2026-01-01T00:00:00+00:00",
        data_snapshot={"source": "fixture"},
        parameters_tested={},
        variant_count=1,
        symbols_tested=(),
        gate_results=(),
        final_status="REJECTED",
        rejection_reasons=("fixture",),
        trial_count_for_family=1,
        trial_count_for_template=1,
        related_rejected_hypotheses=("long_trend",),
        do_not_rerun_until=None,
        requires_new_data_before_rerun=True,
    )
    AlphaResearchMemory(memory_path, ()).add_record(record).write(memory_path)


def _feature_manifest(path_root: Path, **overrides: object) -> Path:
    payload: dict[str, object] = {
        "status": "READY",
        "parity_ok": True,
        "runtime_parity_proven": True,
        "feature_count": 16,
        "feature_snapshot_id": "features_test",
        "fingerprint": "feature-fingerprint",
        "source_snapshot_id": "source-test",
        "source_snapshot_fingerprint": "source-fingerprint",
        "feature_registry_fingerprint": "registry-fingerprint",
        "feature_versions": {"momentum_3_bps": "1.0.0"},
        "ingestion_time_unknown_count": 0,
    }
    payload.update(overrides)
    path = path_root / "feature_snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_ohlcv(tmp_path: Path) -> Path:
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for symbol in ("BTCZEUR", "ETHZEUR"):
        _write_rows(data_dir / f"{symbol}_1h.csv", symbol, "1h", start, 150, timedelta(hours=1))
        _write_rows(data_dir / f"{symbol}_15m.csv", symbol, "15m", start, 600, timedelta(minutes=15))
        _write_rows(data_dir / f"{symbol}_5m.csv", symbol, "5m", start, 1800, timedelta(minutes=5))
    return data_dir


def _write_rows(path: Path, symbol: str, timeframe: str, start: datetime, count: int, step: timedelta) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume"))
        writer.writeheader()
        for index in range(count):
            price = 100.0 + index * 0.1
            writer.writerow(
                {
                    "timestamp": (start + index * step).isoformat(),
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open": f"{price:.6f}",
                    "high": f"{price + 0.2:.6f}",
                    "low": f"{price - 0.2:.6f}",
                    "close": f"{price + 0.1:.6f}",
                    "volume": "100.0",
                }
            )
