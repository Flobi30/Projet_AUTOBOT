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
from autobot.v2.research.alpha_hypothesis_runner import AlphaGateResult, AlphaHypothesisRunnerReport
from autobot.v2.research.bounded_research_coordinator import (
    BoundedResearchCoordinatorConfig,
    run_bounded_research_coordinator,
)
from autobot.v2.research.experiment_registry import ExperimentRegistry, ExperimentSpec
from autobot.v2.research.canonical_feature_snapshot import CanonicalFeatureSnapshotConfig, build_canonical_feature_snapshot
from autobot.v2.research.manifested_experiment import FeatureSnapshotProvenance
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


def test_coordinator_can_run_the_bounded_reversal_adapter_without_execution_paths(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    feature_manifest = _feature_manifest(tmp_path)
    memory_path = tmp_path / "memory.sqlite3"
    _reject_long_trend(memory_path)
    _reject_cross_momentum(memory_path)

    report = run_bounded_research_coordinator(_config(tmp_path, data_dir, feature_manifest, memory_path))

    assert report.decision == "RESEARCH_SMOKE_COMPLETED"
    assert report.selected_hypothesis_id == "mean_reversion_volatility_reversal"
    assert report.selected_template_id == "volatility_reversal_after_extension"
    assert report.runner_report is not None
    assert report.runner_report.paper_capital_allowed is False
    assert report.runner_report.live_allowed is False
    assert report.runner_report.promotable is False


def test_coordinator_runs_only_the_funding_data_check_and_claims_combined_evidence(tmp_path, monkeypatch):
    data_dir = _write_ohlcv(tmp_path)
    config = _config(tmp_path, data_dir, _feature_manifest(tmp_path), tmp_path / "memory.sqlite3")
    derivatives_manifest = tmp_path / "derivatives_forward.json"
    config = replace(
        config,
        scheduler=replace(config.scheduler, derivatives_feature_snapshot_manifest=derivatives_manifest),
    )
    base_scheduler = coordinator.build_alpha_hypothesis_scheduler_report(config.scheduler)
    original = next(item for item in base_scheduler.candidates if item.template_id == "funding_extreme_reversion")
    selected = replace(
        original,
        status="RUNNABLE_DATA_CHECK",
        adapter_ready=True,
        blockers=(),
        warnings=(),
        next_action="run_allowlisted_funding_basis_data_check",
        recommended_command=None,
    )
    monkeypatch.setattr(
        coordinator,
        "build_alpha_hypothesis_scheduler_report",
        lambda _scheduler: replace(base_scheduler, selected=selected),
    )
    captured = {}
    spot = _provenance("spot_snapshot", "spot_fingerprint", "CANONICAL_FEATURE_SNAPSHOT")
    derivatives = _provenance(
        "derivatives_snapshot",
        "derivatives_fingerprint",
        "DERIVATIVES_POINT_IN_TIME",
    )
    template = {
        "template_id": "funding_extreme_reversion",
        "alpha_family_id": "funding_basis",
        "max_variants": 2,
        "max_symbols": 4,
        "max_runtime_seconds": 120,
        "expected_cost_model": "research_stress",
    }
    hypothesis = {"id": "funding_basis", "symbols": ["BTCZEUR"], "timeframe": ["1h"]}
    spec = ExperimentSpec(
        hypothesis_id="funding_basis",
        template_id="funding_extreme_reversion",
        thesis="fixture funding data check",
        code_commit="test-commit",
        image_ref="oci-revision:test-commit",
        data_snapshot_id="combined_fixture",
        feature_versions={"spot_feature": "1.0.0", "funding_rate_relative": "1.0.0"},
        parameters={"mode": "data_check", "max_variants": 0},
        seed=0,
        cost_model={"profile": "research_stress"},
        environment={"research_only": True, "paper_capital_allowed": False, "live_allowed": False, "promotable": False},
        research_campaign_id="family_funding_basis",
    )

    def build_material(*, mode, **_kwargs):
        assert mode == "data_check"
        return template, hypothesis, spec, spot, derivatives, (data_dir,)

    def build_runner(runner_config, *, commit):
        captured["config"] = runner_config
        return AlphaHypothesisRunnerReport(
            run_id=runner_config.run_id,
            generated_at="2026-08-04T00:00:00+00:00",
            commit=commit,
            hypothesis_id="funding_basis",
            requested_hypothesis_id="funding_basis",
            mode="data_check",
            state_db=None,
            data_paths=tuple(str(path) for path in runner_config.data_paths),
            gates=(
                AlphaGateResult(
                    gate="DATA_CHECK",
                    status="KEEP_RESEARCH",
                    passed=True,
                    stopped=False,
                    reasons=("funding_basis_research_inputs_ready",),
                    autonomy_level="AUTO_ALLOWED",
                    risk_direction="neutral",
                    requires_human_approval=False,
                    runtime_seconds=0.0,
                    metrics={"adapter_availability": {"available": True}},
                ),
            ),
            final_status="KEEP_RESEARCH",
            next_allowed_stage="FAST_NET_EDGE_TEST",
            final_decision="NEXT_STAGE_AVAILABLE",
            reasons=("requested_mode_stage_completed",),
            autonomy_policy_summary={},
            runtime_seconds=0.0,
            safety_notes=("research-only fixture",),
        )

    monkeypatch.setattr(coordinator, "_build_material_experiment", build_material)
    monkeypatch.setattr(coordinator, "build_alpha_hypothesis_runner_report", build_runner)

    first = run_bounded_research_coordinator(config)

    assert first.decision == "RESEARCH_DATA_CHECK_COMPLETED"
    assert first.runner_report is not None
    assert first.runner_report.mode == "data_check"
    assert [gate.gate for gate in first.runner_report.gates] == ["DATA_CHECK"]
    assert captured["config"].derivatives_feature_snapshot_manifest == derivatives_manifest
    assert first.experiment_registry_state is not None
    assert first.experiment_registry_state["latest_stage"] == "DATA_CHECK"
    assert first.experiment_registry_state["trial_count"] == 0
    assert first.feature_snapshot is not None
    assert first.feature_snapshot["bounded_claim_snapshot_id"].startswith("combined_")
    assert "derivatives_feature_snapshot" in first.feature_snapshot
    assert not config.memory_path.exists()

    second = run_bounded_research_coordinator(config)

    assert second.decision == "SKIPPED_FEATURE_SNAPSHOT_ALREADY_CLAIMED"
    assert second.runner_report is None


def test_coordinator_rejects_funding_data_check_without_derivatives_evidence(tmp_path, monkeypatch):
    data_dir = _write_ohlcv(tmp_path)
    config = _config(tmp_path, data_dir, _feature_manifest(tmp_path), tmp_path / "memory.sqlite3")
    base_scheduler = coordinator.build_alpha_hypothesis_scheduler_report(config.scheduler)
    original = next(item for item in base_scheduler.candidates if item.template_id == "funding_extreme_reversion")
    selected = replace(original, status="RUNNABLE_DATA_CHECK", adapter_ready=True, blockers=(), warnings=())
    monkeypatch.setattr(
        coordinator,
        "build_alpha_hypothesis_scheduler_report",
        lambda _scheduler: replace(base_scheduler, selected=selected),
    )

    report = run_bounded_research_coordinator(config)

    assert report.decision == "BLOCKED_INVALID_PROVENANCE"
    assert "derivatives feature snapshot is required" in report.reasons[0]
    assert not config.experiment_registry_path.exists()


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
            "--capability-data-paths",
            "data/research/canonical/ohlcv,data/research/manifests",
            "--feature-snapshot-manifest",
            "data/research/manifests/features.json",
            "--derivatives-feature-snapshot-manifest",
            "data/research/manifests/derivatives_forward.json",
            "--image-commit",
            "pytest-image-commit",
        ]
    )

    assert args.command == "bounded-research-coordinator"
    assert args.max_variants == 3
    assert args.max_symbols == 6
    assert args.max_runtime_seconds == 120
    assert args.capability_data_paths == "data/research/canonical/ohlcv,data/research/manifests"
    assert args.derivatives_feature_snapshot_manifest == "data/research/manifests/derivatives_forward.json"
    assert args.image_commit == "pytest-image-commit"
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
        image_commit="test-commit",
        output_dir=tmp_path / "reports",
        memory_path=memory_path,
        experiment_registry_path=tmp_path / "registry.sqlite3",
    )


def _provenance(snapshot_id: str, fingerprint: str, snapshot_kind: str) -> FeatureSnapshotProvenance:
    return FeatureSnapshotProvenance(
        manifest_path=f"/immutable/{snapshot_id}.json",
        feature_snapshot_id=snapshot_id,
        feature_snapshot_fingerprint=fingerprint,
        snapshot_kind=snapshot_kind,
        source_snapshot_id=f"{snapshot_id}_source",
        source_snapshot_fingerprint=f"{fingerprint}_source",
        feature_registry_fingerprint=f"{fingerprint}_registry",
        feature_versions={"fixture_feature": "1.0.0"},
        feature_count=1,
        parity_ok=True,
        ingestion_time_unknown_count=0,
        material_verified=True,
        bundle_content_fingerprint=f"{fingerprint}_bundle",
        runtime_parity_verified=True,
    )


def test_coordinator_blocks_before_registry_writes_when_image_commit_differs(tmp_path):
    config = _config(
        tmp_path,
        tmp_path / "missing-data",
        tmp_path / "missing-manifest.json",
        tmp_path / "memory.sqlite3",
    )
    report = run_bounded_research_coordinator(replace(config, image_commit="other-image-commit"))

    assert report.decision == "BLOCKED_IMAGE_PROVENANCE_MISMATCH"
    assert report.image_provenance_verified is False
    assert "image_commit_does_not_match_declared_code_commit" in report.reasons
    assert not config.experiment_registry_path.exists()
    assert not config.memory_path.exists()


def _reject_long_trend(memory_path: Path) -> None:
    _reject_hypothesis(
        memory_path,
        hypothesis_id="long_trend",
        alpha_family_id="trend_momentum",
        template_id="regime_filtered_trend",
    )


def _reject_cross_momentum(memory_path: Path) -> None:
    _reject_hypothesis(
        memory_path,
        hypothesis_id="cross_momentum",
        alpha_family_id="cross_sectional_momentum",
        template_id="leader_laggard_momentum",
    )


def _reject_hypothesis(
    memory_path: Path,
    *,
    hypothesis_id: str,
    alpha_family_id: str,
    template_id: str,
) -> None:
    record = ResearchMemoryRecord(
        run_id=f"historical_{hypothesis_id}_reject",
        hypothesis_id=hypothesis_id,
        alpha_family_id=alpha_family_id,
        template_id=template_id,
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
        related_rejected_hypotheses=(hypothesis_id,),
        do_not_rerun_until=None,
        requires_new_data_before_rerun=True,
    )
    AlphaResearchMemory(memory_path, ()).add_record(record).write(memory_path)


def _feature_manifest(path_root: Path, **overrides: object) -> Path:
    source = path_root / "feature_source.csv"
    fields = (
        "exchange",
        "market_type",
        "symbol",
        "base_asset",
        "quote_asset",
        "market_mapping_status",
        "timeframe",
        "event_time",
        "available_time",
        "ingestion_time",
        "close",
    )
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(30):
            timestamp = origin + timedelta(minutes=index * 5)
            writer.writerow(
                {
                    "exchange": "kraken",
                    "market_type": "spot",
                    "symbol": "BTCEUR",
                    "base_asset": "BTC",
                    "quote_asset": "EUR",
                    "market_mapping_status": "EXPLICIT",
                    "timeframe": "5m",
                    "event_time": timestamp.isoformat(),
                    "available_time": timestamp.isoformat(),
                    "ingestion_time": timestamp.isoformat(),
                    "close": str(100 + index),
                }
            )
    canonical_manifest = path_root / "feature_source_manifest.json"
    canonical_manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "snapshot_id": "source-test",
                "fingerprint": "source-fingerprint",
                "market_type": "spot",
                "files": [{"csv_path": str(source)}],
            }
        ),
        encoding="utf-8",
    )
    snapshot = build_canonical_feature_snapshot(
        CanonicalFeatureSnapshotConfig(
            run_id="bounded_research_features",
            canonical_manifest_path=canonical_manifest,
            output_dir=path_root / "features",
            manifest_dir=path_root / "feature_manifests",
        )
    )
    path = Path(str(snapshot.manifest_path))
    payload: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_ohlcv(tmp_path: Path) -> Path:
    data_dir = tmp_path / "source-test"
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
