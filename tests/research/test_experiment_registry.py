from __future__ import annotations

import ast
import sqlite3
from types import SimpleNamespace
from pathlib import Path

import pytest

from autobot.v2.research.experiment_registry import (
    ExperimentRegistry,
    ExperimentRegistryError,
    ExperimentSpec,
)


pytestmark = pytest.mark.unit


def _spec(*, snapshot: str = "ohlcv_v2_snapshot", thesis: str = "funding mean reversion") -> ExperimentSpec:
    return ExperimentSpec(
        hypothesis_id="funding_basis",
        template_id="funding_extreme_reversion",
        thesis=thesis,
        code_commit="c42ab43",
        image_ref="projet_autobot-autobot@sha256:test",
        data_snapshot_id=snapshot,
        feature_versions={"funding_rate_relative": "1.0.0", "basis_bps": "1.0.0"},
        parameters={"threshold": 2.5, "lookback": 24},
        seed=42,
        cost_model={"fee_bps": 16.0, "slippage_bps": 9.0},
        environment={"python": "3.11", "mode": "research"},
        holdout_id="holdout_2026_q3",
    )


def test_experiment_registry_is_idempotent_and_tracks_all_trial_dimensions(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiment_registry.sqlite3")
    first = registry.register_experiment(_spec())
    second = registry.register_experiment(_spec())

    assert first.experiment_id == second.experiment_id
    registry.record_trial(experiment_id=first.experiment_id, dimension="parameter", value={"threshold": 2.5})
    registry.record_trial(experiment_id=first.experiment_id, dimension="pair", value="BTCZEUR")
    registry.record_trial(experiment_id=first.experiment_id, dimension="timeframe", value="1h")
    registry.record_trial(experiment_id=first.experiment_id, dimension="regime", value="range")

    state = registry.get_state(first.experiment_id)
    assert state.trial_count == 4
    assert registry.trial_count(hypothesis_id="funding_basis") == 4
    assert registry.validation_trial_count(hypothesis_id="funding_basis") == 4
    assert state.paper_capital_allowed is False
    assert state.live_allowed is False


def test_trial_plan_is_idempotent_and_counts_candidate_configurations_across_experiments(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    first = registry.register_experiment(_spec(snapshot="ohlcv_v2_first"))

    assert registry.record_trial_plan(
        experiment_id=first.experiment_id,
        variant_count=2,
        symbols=("BTCZEUR", "ETHZEUR"),
        timeframes=("1h", "15m"),
        regimes=("trend",),
    ) == 8
    assert registry.record_trial_plan(
        experiment_id=first.experiment_id,
        variant_count=2,
        symbols=("ETHZEUR", "BTCZEUR"),
        timeframes=("15m", "1h"),
        regimes=("trend",),
    ) == 8
    assert registry.validation_trial_count(hypothesis_id="funding_basis") == 8

    second = registry.register_experiment(_spec(snapshot="ohlcv_v2_second"))
    registry.record_trial_plan(
        experiment_id=second.experiment_id,
        variant_count=1,
        symbols=("BTCZEUR",),
        timeframes=("1h",),
        regimes=(),
    )
    assert registry.validation_trial_count(hypothesis_id="funding_basis") == 9
    assert registry.trial_count(hypothesis_id="funding_basis") == 19


def test_bounded_research_execution_claim_is_atomic_and_append_only(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    experiment = registry.register_experiment(_spec())

    assert registry.claim_bounded_research_execution(
        experiment_id=experiment.experiment_id,
        coordinator_run_id="daily_2026_07_16",
    ) is True
    assert registry.claim_bounded_research_execution(
        experiment_id=experiment.experiment_id,
        coordinator_run_id="daily_2026_07_16_retry",
    ) is False

    manifest = registry.export_manifest(experiment.experiment_id)
    assert manifest["bounded_research_execution_claim"]["coordinator_run_id"] == "daily_2026_07_16"
    with sqlite3.connect(registry.path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM bounded_research_execution_claims")


def test_bounded_research_snapshot_claim_allows_one_automatic_attempt_per_snapshot(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")

    assert registry.claim_bounded_research_snapshot(
        feature_snapshot_id="features_2026_07_16",
        feature_snapshot_fingerprint="snapshot-fingerprint",
        coordinator_run_id="daily_2026_07_16",
    ) is True
    assert registry.claim_bounded_research_snapshot(
        feature_snapshot_id="features_2026_07_16",
        feature_snapshot_fingerprint="snapshot-fingerprint",
        coordinator_run_id="daily_2026_07_16_retry",
    ) is False
    with sqlite3.connect(registry.path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM bounded_research_snapshot_claims")


def test_registry_enforces_monotonic_gate_pipeline_and_terminal_rejection(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    experiment = registry.register_experiment(_spec())

    with pytest.raises(ExperimentRegistryError, match="expected stage DATA_CHECK"):
        registry.record_gate_result(experiment_id=experiment.experiment_id, stage="NET_SMOKE", status="PASSED")

    registry.record_gate_result(experiment_id=experiment.experiment_id, stage="DATA_CHECK", status="PASSED")
    registry.record_gate_result(experiment_id=experiment.experiment_id, stage="NET_SMOKE", status="REJECTED", reasons=("net_pf_below_one",))
    state = registry.get_state(experiment.experiment_id)

    assert state.latest_stage == "NET_SMOKE"
    assert state.latest_status == "REJECTED"
    assert state.terminal is True
    with pytest.raises(ExperimentRegistryError, match="terminal experiment"):
        registry.record_trial(experiment_id=experiment.experiment_id, dimension="parameter", value={"threshold": 3.0})


def test_final_shadow_review_closes_the_material_experiment(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    experiment = registry.register_experiment(_spec())
    for stage in ("DATA_CHECK", "NET_SMOKE", "WALK_FORWARD", "STRESS_MONTE_CARLO"):
        state = registry.record_gate_result(experiment_id=experiment.experiment_id, stage=stage, status="PASSED")

    with pytest.raises(ExperimentRegistryError, match="immutable final holdout review"):
        registry.record_gate_result(experiment_id=experiment.experiment_id, stage="SHADOW_REVIEW", status="PASSED")

    registry.reserve_holdout(
        holdout_id="holdout_2026_q3",
        data_snapshot_id="ohlcv_v2_holdout",
        immutable_fingerprint="fingerprint-holdout",
    )
    registry.record_final_holdout_review(
        experiment_id=experiment.experiment_id,
        metrics={"net_pnl_eur": 4.5, "profit_factor": 1.2},
        reasons=("final_immutable_holdout",),
    )
    state = registry.record_gate_result(experiment_id=experiment.experiment_id, stage="SHADOW_REVIEW", status="PASSED")

    assert state.terminal is True
    assert registry.has_final_holdout_review(experiment.experiment_id) is True
    with pytest.raises(ExperimentRegistryError, match="terminal experiment"):
        registry.record_gate_result(experiment_id=experiment.experiment_id, stage="DATA_CHECK", status="PASSED")


def test_immutable_holdout_cannot_be_used_for_optimization(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    experiment = registry.register_experiment(_spec())

    assert registry.reserve_holdout(
        holdout_id="holdout_2026_q3",
        data_snapshot_id="ohlcv_v2_holdout",
        immutable_fingerprint="fingerprint-holdout",
        manifest={"period": "2026-Q3", "symbols": ["BTCZEUR"]},
    ) is True
    assert registry.reserve_holdout(
        holdout_id="holdout_2026_q3",
        data_snapshot_id="ohlcv_v2_holdout",
        immutable_fingerprint="fingerprint-holdout",
        manifest={"period": "2026-Q3", "symbols": ["BTCZEUR"]},
    ) is False
    with pytest.raises(ExperimentRegistryError, match="immutable holdout"):
        registry.record_trial(
            experiment_id=experiment.experiment_id,
            dimension="parameter",
            value={"threshold": 4.0},
            uses_holdout=True,
            optimization=True,
        )

    registry.record_trial(
        experiment_id=experiment.experiment_id,
        dimension="final_holdout_review",
        value={"status": "observed"},
        uses_holdout=True,
        optimization=False,
    )
    assert registry.get_state(experiment.experiment_id).trial_count == 1


def test_holdout_requires_prior_reservation_and_matching_experiment_reference(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    experiment = registry.register_experiment(_spec())

    with pytest.raises(ExperimentRegistryError, match="must be reserved"):
        registry.record_trial(
            experiment_id=experiment.experiment_id,
            dimension="final_holdout_review",
            value={"status": "observed"},
            uses_holdout=True,
            optimization=False,
        )

    registry.reserve_holdout(
        holdout_id="holdout_2026_q3",
        data_snapshot_id="ohlcv_v2_holdout",
        immutable_fingerprint="fingerprint-holdout",
    )
    with pytest.raises(ExperimentRegistryError, match="does not match"):
        registry.record_trial(
            experiment_id=experiment.experiment_id,
            dimension="final_holdout_review",
            value={"status": "observed"},
            uses_holdout=True,
            optimization=False,
            holdout_id="different_holdout",
        )


def test_registry_tables_reject_update_and_delete_after_recording(tmp_path):
    path = tmp_path / "registry.sqlite3"
    registry = ExperimentRegistry(path)
    experiment = registry.register_experiment(_spec())
    registry.record_trial(experiment_id=experiment.experiment_id, dimension="pair", value="BTCZEUR")

    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM experiment_trials")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE experiments SET hypothesis_id = 'tampered'")


def test_runner_projection_counts_bounded_dimensions_and_normalizes_legacy_stage_names(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    report = SimpleNamespace(
        run_id="funding_smoke_01",
        gates=(
            SimpleNamespace(gate="DATA_CHECK", status="PASSED", passed=True, metrics={}, reasons=()),
            SimpleNamespace(gate="FAST_NET_EDGE_TEST", status="DATA_MISSING", passed=False, metrics={}, reasons=("no_basis_history",)),
        ),
    )

    state = registry.record_runner_evidence(
        spec=_spec(),
        report=report,
        variant_count=2,
        symbols=("btcz eur".replace(" ", ""), "ETHZEUR"),
    )

    assert state.latest_stage == "NET_SMOKE"
    assert state.latest_status == "INSUFFICIENT_DATA"
    assert state.trial_count == 8
    assert registry.validation_trial_count(hypothesis_id="funding_basis") == 4
    assert state.terminal is True


def test_block2_research_modules_do_not_import_runtime_order_paths():
    root = Path(__file__).resolve().parents[2]
    forbidden = {"autobot.v2.order_router", "autobot.v2.signal_handler_async", "autobot.v2.kraken_client"}
    modules = (
        "src/autobot/v2/research/experiment_registry.py",
        "src/autobot/v2/research/statistical_validation.py",
        "src/autobot/v2/research/robustness_experiments.py",
    )

    for relative in modules:
        imports = {
            alias.name
            for node in ast.walk(ast.parse((root / relative).read_text(encoding="utf-8")))
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module
            for node in ast.walk(ast.parse((root / relative).read_text(encoding="utf-8")))
            if isinstance(node, ast.ImportFrom) and node.module
        )
        assert imports.isdisjoint(forbidden), relative


def test_legacy_memory_migration_is_append_only_and_manifest_is_reproducible(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    records = (
        {"run_id": "legacy-1", "hypothesis_id": "trend_momentum", "final_status": "REJECTED"},
        {"run_id": "legacy-2", "hypothesis_id": "mean_reversion", "final_status": "INSUFFICIENT_DATA"},
    )
    assert registry.migrate_legacy_memory(records) == 2
    assert registry.migrate_legacy_memory(records) == 0

    experiment = registry.register_experiment(_spec(snapshot="ohlcv_v2_manifest"))
    registry.record_gate_result(experiment_id=experiment.experiment_id, stage="DATA_CHECK", status="PASSED")
    manifest = registry.export_manifest(experiment.experiment_id)

    assert manifest["experiment"]["data_snapshot_id"] == "ohlcv_v2_manifest"
    assert manifest["state"]["latest_stage"] == "DATA_CHECK"
    assert manifest["research_only"] is True
    assert manifest["paper_capital_allowed"] is False
    assert manifest["live_allowed"] is False
