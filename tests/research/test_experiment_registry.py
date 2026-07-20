from __future__ import annotations

import ast
from dataclasses import asdict
from hashlib import sha256
import json
import sqlite3
from types import SimpleNamespace
from pathlib import Path

import pytest

from autobot.v2.research.experiment_registry import (
    ExperimentRegistry,
    ExperimentRegistryError,
    ExperimentSpec,
    _fingerprint,
)
from autobot.v2.research.shadow_review_evidence import seal_shadow_review_evidence


pytestmark = pytest.mark.unit


def _holdout_partition() -> dict[str, object]:
    return {
        "schema_version": 1,
        "partition_id": "holdout_2026_q3",
        "fingerprint": "holdout-2026-q3-fixture-fingerprint",
        "holdout_snapshot_id": "holdout_2026_q3_review",
        "holdout_snapshot_fingerprint": "holdout-2026-q3-review-fingerprint",
        "source_snapshot_id": "ohlcv_v2_snapshot",
        "source_snapshot_fingerprint": "ohlcv-v2-fixture-fingerprint",
    }


def _holdout_provenance(experiment_id: str) -> dict[str, object]:
    partition = _holdout_partition()
    identity = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "partition_id": partition["partition_id"],
        "partition_fingerprint": partition["fingerprint"],
        "holdout_snapshot_id": partition["holdout_snapshot_id"],
        "holdout_snapshot_fingerprint": partition["holdout_snapshot_fingerprint"],
        "source_snapshot_id": partition["source_snapshot_id"],
        "source_snapshot_fingerprint": partition["source_snapshot_fingerprint"],
        "code_commit": "c42ab43",
        "feature_versions": {"basis_bps": "1.0.0", "funding_rate_relative": "1.0.0"},
        "parameter_fingerprint": sha256(
            json.dumps({"threshold": 2.5, "lookback": 24}, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "cost_model_fingerprint": sha256(
            json.dumps({"fee_bps": 16.0, "slippage_bps": 9.0}, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    return {
        **identity,
        "fingerprint": sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }


def _holdout_artifact(experiment_id: str, *, net_pnl_eur: float = 4.5) -> dict[str, object]:
    return {
        "holdout_partition": _holdout_partition(),
        "role": "holdout_review",
        "result_fingerprint": "pytest-final-result-fingerprint",
        "sha256": "pytest-final-result-sha256",
        "data_root": "/sealed/holdout",
        "shadow_review_evidence": seal_shadow_review_evidence(
            experiment_id=experiment_id,
            holdout_evaluation={
                "verdict": "HOLDOUT_PASSED_RESEARCH_ONLY",
                "blockers": [],
                "trade_count": 50,
                "net_pnl_eur": net_pnl_eur,
                "provenance": _holdout_provenance(experiment_id),
                "research_only": True,
                "paper_capital_allowed": False,
                "live_allowed": False,
                "promotable": False,
            },
            statistical_gate_summary={
                "decision": "SHADOW_REVIEW_ELIGIBLE",
                "blockers": [],
                "shadow_review_eligible": True,
                "trade_count": 50,
                "trial_count": 8,
                "net_pnl_eur": net_pnl_eur,
                "out_of_sample_confirmed": True,
                "net_of_costs": True,
                "research_only": True,
                "paper_capital_allowed": False,
                "live_allowed": False,
                "promotable": False,
            },
        ),
    }


def _spec(
    *,
    snapshot: str = "ohlcv_v2_snapshot",
    thesis: str = "funding mean reversion",
    hypothesis_id: str = "funding_basis",
    template_id: str = "funding_extreme_reversion",
    research_campaign_id: str | None = None,
) -> ExperimentSpec:
    return ExperimentSpec(
        hypothesis_id=hypothesis_id,
        template_id=template_id,
        thesis=thesis,
        code_commit="c42ab43",
        image_ref="projet_autobot-autobot@sha256:test",
        data_snapshot_id=snapshot,
        feature_versions={"funding_rate_relative": "1.0.0", "basis_bps": "1.0.0"},
        parameters={"threshold": 2.5, "lookback": 24},
        seed=42,
        cost_model={"fee_bps": 16.0, "slippage_bps": 9.0},
        environment={"python": "3.11", "mode": "research", "holdout_partition": _holdout_partition()},
        holdout_id="holdout_2026_q3",
        research_campaign_id=research_campaign_id,
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


def test_validation_trial_count_uses_explicit_campaign_without_mixing_legacy_rows(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    campaign = "family_funding_basis"
    first = registry.register_experiment(
        _spec(snapshot="ohlcv_v2_first", research_campaign_id=campaign)
    )
    registry.record_trial_plan(
        experiment_id=first.experiment_id,
        variant_count=2,
        symbols=("BTCZEUR", "ETHZEUR"),
        timeframes=("1h",),
    )
    second = registry.register_experiment(
        _spec(
            snapshot="ohlcv_v2_second",
            hypothesis_id="basis_reversion_variant",
            template_id="basis_reversion_variant",
            research_campaign_id=campaign,
        )
    )
    registry.record_trial_plan(
        experiment_id=second.experiment_id,
        variant_count=1,
        symbols=("BTCZEUR",),
        timeframes=("1h",),
    )
    legacy = registry.register_experiment(_spec(snapshot="ohlcv_v2_legacy"))
    registry.record_trial_plan(
        experiment_id=legacy.experiment_id,
        variant_count=5,
        symbols=("BTCZEUR",),
        timeframes=("1h",),
    )

    assert registry.validation_trial_count(hypothesis_id="funding_basis") == 9
    assert registry.validation_trial_count(
        hypothesis_id="funding_basis",
        research_campaign_id=campaign,
    ) == 5
    with pytest.raises(ExperimentRegistryError, match="research_campaign_id"):
        registry.validation_trial_count(hypothesis_id="funding_basis", research_campaign_id="unsafe scope")


def test_campaign_schema_migrates_an_existing_append_only_registry_without_rewriting_rows(tmp_path):
    path = tmp_path / "legacy_registry.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE experiments (
                experiment_id TEXT PRIMARY KEY,
                material_fingerprint TEXT NOT NULL UNIQUE,
                hypothesis_id TEXT NOT NULL,
                template_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                spec_json TEXT NOT NULL,
                research_only INTEGER NOT NULL CHECK (research_only = 1),
                paper_capital_allowed INTEGER NOT NULL CHECK (paper_capital_allowed = 0),
                live_allowed INTEGER NOT NULL CHECK (live_allowed = 0),
                promotable INTEGER NOT NULL CHECK (promotable = 0)
            )
            """
        )
    registry = ExperimentRegistry(path)
    state = registry.register_experiment(_spec(research_campaign_id="family_funding_basis"))

    with sqlite3.connect(path) as connection:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(experiments)")}
        stored_campaign = connection.execute(
            "SELECT research_campaign_id FROM experiments WHERE experiment_id = ?",
            (state.experiment_id,),
        ).fetchone()[0]
    assert "research_campaign_id" in columns
    assert stored_campaign == "family_funding_basis"


def test_legacy_experiment_identity_remains_stable_when_no_campaign_is_declared():
    spec = _spec()
    historical_payload = asdict(spec)
    historical_payload.pop("research_campaign_id")

    assert spec.material_fingerprint == _fingerprint(historical_payload)


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
        immutable_fingerprint=str(_holdout_partition()["fingerprint"]),
        manifest={"partition": _holdout_partition()},
    )
    with pytest.raises(ExperimentRegistryError, match="artifact partition"):
        registry.record_final_holdout_review(
            experiment_id=experiment.experiment_id,
            metrics={"net_pnl_eur": 4.5, "profit_factor": 1.2},
            artifact={**_holdout_artifact(experiment.experiment_id), "holdout_partition": {"partition_id": "other"}},
        )
    registry.record_final_holdout_review(
        experiment_id=experiment.experiment_id,
        metrics={"net_pnl_eur": 4.5, "profit_factor": 1.2},
        reasons=("final_immutable_holdout",),
        artifact=_holdout_artifact(experiment.experiment_id),
    )
    with pytest.raises(ExperimentRegistryError, match="already recorded"):
        registry.record_final_holdout_review(
            experiment_id=experiment.experiment_id,
            metrics={"net_pnl_eur": 5.0, "profit_factor": 1.3},
            artifact=_holdout_artifact(experiment.experiment_id, net_pnl_eur=5.0),
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

    with pytest.raises(ExperimentRegistryError, match="must be recorded through record_final_holdout_review"):
        registry.record_trial(
            experiment_id=experiment.experiment_id,
            dimension="final_holdout_review",
            value={"status": "observed"},
            uses_holdout=True,
            optimization=False,
        )
    assert registry.get_state(experiment.experiment_id).trial_count == 0


def test_holdout_requires_prior_reservation_and_matching_experiment_reference(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    experiment = registry.register_experiment(_spec())

    with pytest.raises(ExperimentRegistryError, match="must be reserved"):
        registry.record_trial(
            experiment_id=experiment.experiment_id,
            dimension="holdout_observation",
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
            dimension="holdout_observation",
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


def test_runner_evidence_binds_written_reports_as_content_addressed_artifacts(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    json_report = tmp_path / "runner.json"
    markdown_report = tmp_path / "runner.md"
    json_report.write_text('{"result":"fixed"}', encoding="utf-8")
    markdown_report.write_text("# Fixed runner evidence\n", encoding="utf-8")
    report = SimpleNamespace(
        run_id="funding_smoke_written",
        json_report_path=str(json_report),
        markdown_report_path=str(markdown_report),
        gates=(
            SimpleNamespace(gate="DATA_CHECK", status="PASSED", passed=True, metrics={}, reasons=()),
            SimpleNamespace(gate="NET_SMOKE", status="REJECTED", passed=False, metrics={}, reasons=("net_pf_below_one",)),
        ),
    )

    state = registry.record_runner_evidence(
        spec=_spec(),
        report=report,
        variant_count=1,
        symbols=("BTCZEUR",),
    )

    artifacts = registry.export_manifest(state.experiment_id)["artifacts"]
    assert {(item["metadata"]["kind"], item["fingerprint"]) for item in artifacts} == {
        ("runner_json_report", sha256(json_report.read_bytes()).hexdigest()),
        ("runner_markdown_report", sha256(markdown_report.read_bytes()).hexdigest()),
    }
    assert all(item["stage"] == "DATA_CHECK" for item in artifacts)


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
