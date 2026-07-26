from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.regime_features import RegimeFeatureConfig, RegimeFeatureEngine
from autobot.v2.research.market_data_repository import MarketBar
from autobot.v2.research.experiment_registry import ExperimentRegistry, ExperimentRegistryError, ExperimentSpec
from autobot.v2.research.regime_context import enrich_bars_with_regime_context
from autobot.v2.research.regime_context import (
    BoundedRegimeSegmentation,
    record_regime_segmentation_experiment_trial,
    record_regime_segmentation_trial,
)


pytestmark = pytest.mark.integration


def _bar(index, close, *, metadata=None):
    timestamp = datetime(2026, 6, 2, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=index)
    return MarketBar(
        timestamp=timestamp,
        symbol="TRXEUR",
        timeframe="1m",
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
        metadata=dict(metadata or {}),
    )


def _engine():
    return RegimeFeatureEngine(
        RegimeFeatureConfig(
            min_samples=2,
            entropy_window=4,
            markov_window=4,
            flat_return_bps=2.0,
            volatile_return_bps=250.0,
        )
    )


def _experiment_spec(snapshot_id: str) -> ExperimentSpec:
    return ExperimentSpec(
        hypothesis_id="regime_filter_research",
        template_id="regime_filtered_trend",
        thesis="Regime segmentation is a bounded research dimension.",
        code_commit="pytest",
        image_ref="pytest-image",
        data_snapshot_id=snapshot_id,
        feature_versions={"regime_features": "1.0.0"},
        parameters={"lookback": 32},
        seed=42,
        cost_model={"fee_bps": 20.0},
        environment={"mode": "research"},
    )


def test_regime_context_uses_only_observed_history_per_bar():
    bars = [_bar(index, close) for index, close in enumerate([100.0, 101.0, 102.0, 103.0])]

    enriched = enrich_bars_with_regime_context(bars, regime_engine=_engine())

    first_context = enriched[0].metadata["regime_context"]
    last_context = enriched[-1].metadata["regime_context"]

    assert first_context["sample_count"] == 0
    assert first_context["reason"] == "insufficient_samples"
    assert last_context["sample_count"] == 3
    assert last_context["regime"] == "trend"
    assert enriched[-1].metadata["regime"] == "trend"
    assert enriched[-1].metadata["regime_source"] == "research_regime_features"


def test_regime_context_preserves_explicit_non_unknown_regime_label():
    bars = [_bar(index, close, metadata={"regime": "manual_range"}) for index, close in enumerate([100.0, 101.0, 102.0])]

    enriched = enrich_bars_with_regime_context(bars, regime_engine=_engine())

    assert enriched[-1].metadata["regime"] == "manual_range"
    assert enriched[-1].metadata["regime_context"]["regime"] == "trend"


def test_regime_segmentations_are_bounded_and_recorded_as_idempotent_trials(tmp_path):
    segmentation = BoundedRegimeSegmentation(
        segmentation_id="default_market_regimes",
        version="1.0.0",
        labels=("trend", "range", "high_vol", "chaos"),
    )
    path = tmp_path / "regime_trials.jsonl"

    first = record_regime_segmentation_trial(path=path, segmentation=segmentation, snapshot_id="snapshot-1")
    second = record_regime_segmentation_trial(path=path, segmentation=segmentation, snapshot_id="snapshot-1")

    assert first["trial_id"] == second["trial_id"]
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    with pytest.raises(ValueError, match="max_segments"):
        BoundedRegimeSegmentation("too_many", "1", tuple(str(index) for index in range(7)))


def test_regime_segmentation_is_a_snapshot_bound_idempotent_experiment_trial(tmp_path):
    snapshot_id = "canonical_ohlcv_v2"
    registry = ExperimentRegistry(tmp_path / "experiment_registry.sqlite3")
    experiment = registry.register_experiment(_experiment_spec(snapshot_id))
    segmentation = BoundedRegimeSegmentation(
        segmentation_id="default_market_regimes",
        version="1.0.0",
        labels=("trend", "range", "high_vol", "chaos"),
    )

    first = record_regime_segmentation_experiment_trial(
        registry=registry,
        experiment_id=experiment.experiment_id,
        segmentation=segmentation,
        snapshot_id=snapshot_id,
    )
    second = record_regime_segmentation_experiment_trial(
        registry=registry,
        experiment_id=experiment.experiment_id,
        segmentation=segmentation,
        snapshot_id=snapshot_id,
    )

    assert first["trial_id"] == second["trial_id"]
    manifest = registry.export_manifest(experiment.experiment_id)
    segmentation_trials = [trial for trial in manifest["trials"] if trial["dimension"] == "regime_segmentation"]
    assert len(segmentation_trials) == 1
    assert segmentation_trials[0]["value"]["data_snapshot_id"] == snapshot_id
    assert segmentation_trials[0]["value"]["labels"] == ["trend", "range", "high_vol", "chaos"]
    assert segmentation_trials[0]["value"]["paper_capital_allowed"] is False
    assert registry.validation_trial_count(hypothesis_id="regime_filter_research") == 1


def test_regime_segmentation_rejects_a_mismatched_snapshot_or_terminal_experiment(tmp_path):
    snapshot_id = "canonical_ohlcv_v2"
    registry = ExperimentRegistry(tmp_path / "experiment_registry.sqlite3")
    experiment = registry.register_experiment(_experiment_spec(snapshot_id))
    segmentation = BoundedRegimeSegmentation("default_market_regimes", "1.0.0", ("trend", "range"))

    with pytest.raises(ExperimentRegistryError, match="data_snapshot_id"):
        record_regime_segmentation_experiment_trial(
            registry=registry,
            experiment_id=experiment.experiment_id,
            segmentation=segmentation,
            snapshot_id="another_snapshot",
        )

    registry.record_gate_result(
        experiment_id=experiment.experiment_id,
        stage="DATA_CHECK",
        status="INSUFFICIENT_DATA",
    )
    with pytest.raises(ExperimentRegistryError, match="terminal experiment"):
        record_regime_segmentation_experiment_trial(
            registry=registry,
            experiment_id=experiment.experiment_id,
            segmentation=segmentation,
            snapshot_id=snapshot_id,
        )

