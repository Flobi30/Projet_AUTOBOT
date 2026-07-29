"""Research-only market-regime enrichment for validation replays.

The helpers in this module attach Markov/entropy regime context to replay
``MarketBar`` objects without touching runtime paper/live execution. Enrichment
is chronological per symbol, so a bar never receives information from future
bars.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import replace
from typing import TYPE_CHECKING, Sequence

from autobot.v2.regime_features import RegimeFeatureConfig, RegimeFeatureEngine

from .market_data_repository import MarketBar, MarketDataRepository

if TYPE_CHECKING:
    from .experiment_registry import ExperimentRegistry


@dataclass(frozen=True)
class BoundedRegimeSegmentation:
    """Versioned research segmentation; every non-default split is a trial."""

    segmentation_id: str
    version: str
    labels: tuple[str, ...]
    max_segments: int = 6

    def __post_init__(self) -> None:
        labels = tuple(str(label).strip().lower() for label in self.labels if str(label).strip())
        if not self.segmentation_id.strip() or not self.version.strip():
            raise ValueError("segmentation_id and version are required")
        if not labels or len(labels) > self.max_segments:
            raise ValueError("segmentation labels must be between 1 and max_segments")
        if len(set(labels)) != len(labels):
            raise ValueError("segmentation labels must be unique")
        object.__setattr__(self, "labels", labels)

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


DEFAULT_RESEARCH_REGIME_SEGMENTATION = BoundedRegimeSegmentation(
    segmentation_id="research_market_regimes",
    version="1.0.0",
    labels=("trend", "range", "high_vol", "chaos", "low_activity", "unknown"),
)


def _feature_config_fingerprint(config: RegimeFeatureConfig) -> str:
    """Return a stable identity for research-only regime feature settings."""

    payload = json.dumps(asdict(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _default_research_regime_engine() -> RegimeFeatureEngine:
    """Use a fixed baseline and never runtime environment feature flags."""

    return RegimeFeatureEngine(RegimeFeatureConfig())


def record_regime_segmentation_trial(
    *,
    path: str | Path,
    segmentation: BoundedRegimeSegmentation,
    snapshot_id: str,
    outcome: str = "PENDING",
    feature_config: RegimeFeatureConfig | None = None,
) -> dict[str, str]:
    """Append an idempotent research trial record without touching runtime."""

    feature_config_fingerprint = _feature_config_fingerprint(feature_config or RegimeFeatureConfig())
    trial = {
        "trial_id": f"regime_{segmentation.fingerprint[:12]}_{feature_config_fingerprint[:12]}_{snapshot_id}",
        "segmentation_id": segmentation.segmentation_id,
        "segmentation_version": segmentation.version,
        "segmentation_fingerprint": segmentation.fingerprint,
        "feature_config_fingerprint": feature_config_fingerprint,
        "snapshot_id": str(snapshot_id),
        "outcome": str(outcome).upper(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    if destination.exists():
        for line in destination.read_text(encoding="utf-8").splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("trial_id"):
                existing_ids.add(str(payload["trial_id"]))
    if trial["trial_id"] not in existing_ids:
        with destination.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(trial, sort_keys=True))
            handle.write("\n")
    return trial


def record_regime_segmentation_experiment_trial(
    *,
    registry: "ExperimentRegistry",
    experiment_id: str,
    segmentation: BoundedRegimeSegmentation,
    snapshot_id: str,
    feature_config: RegimeFeatureConfig | None = None,
) -> dict[str, str]:
    """Bind one bounded regime split to the canonical experiment registry.

    This is the authoritative path for a segmentation used in validation.  It
    records a research-only optimization trial before any result is inspected,
    so regime slicing cannot become an uncounted route to parameter fishing.
    It does not run a strategy, alter a runtime regime, or change promotion.
    """

    feature_config_fingerprint = _feature_config_fingerprint(feature_config or RegimeFeatureConfig())
    trial_id = registry.record_regime_segmentation_trial(
        experiment_id=experiment_id,
        segmentation_id=segmentation.segmentation_id,
        segmentation_version=segmentation.version,
        segmentation_fingerprint=segmentation.fingerprint,
        labels=segmentation.labels,
        max_segments=segmentation.max_segments,
        data_snapshot_id=snapshot_id,
        feature_config_fingerprint=feature_config_fingerprint,
    )
    return {
        "trial_id": trial_id,
        "experiment_id": str(experiment_id),
        "segmentation_id": segmentation.segmentation_id,
        "segmentation_version": segmentation.version,
        "segmentation_fingerprint": segmentation.fingerprint,
        "feature_config_fingerprint": feature_config_fingerprint,
        "snapshot_id": str(snapshot_id),
        "research_only": "true",
    }


def enrich_bars_with_regime_context(
    bars: Sequence[MarketBar],
    *,
    regime_engine: RegimeFeatureEngine | None = None,
    segmentation: BoundedRegimeSegmentation = DEFAULT_RESEARCH_REGIME_SEGMENTATION,
    experiment_registry: "ExperimentRegistry | None" = None,
    experiment_id: str | None = None,
    snapshot_id: str | None = None,
) -> list[MarketBar]:
    """Return point-in-time, research-only regime metadata.

    The built-in segmentation is a fixed baseline. Any supplied engine or
    segmentation changes the research decision surface and must be recorded as
    an experiment trial before its result can be inspected. This path never
    reads runtime environment flags or changes runtime/paper/live behaviour.
    """

    engine = regime_engine or _default_research_regime_engine()
    custom_context = (
        regime_engine is not None
        or segmentation.fingerprint != DEFAULT_RESEARCH_REGIME_SEGMENTATION.fingerprint
    )
    trial: dict[str, str] | None = None
    if custom_context:
        if (
            experiment_registry is None
            or not str(experiment_id or "").strip()
            or not str(snapshot_id or "").strip()
        ):
            raise ValueError(
                "custom regime context requires experiment_registry, experiment_id and snapshot_id"
            )
        trial = record_regime_segmentation_experiment_trial(
            registry=experiment_registry,
            experiment_id=str(experiment_id),
            segmentation=segmentation,
            snapshot_id=str(snapshot_id),
            feature_config=engine.config,
        )
    config_fingerprint = _feature_config_fingerprint(engine.config)
    repository = MarketDataRepository()
    ordered_bars = repository.normalize(bars)
    history_by_market_timeframe: dict[tuple[str, str], list[float]] = {}
    enriched: list[MarketBar] = []

    for bar in ordered_bars:
        symbol = bar.symbol.upper()
        key = (symbol, str(bar.timeframe))
        price_history = history_by_market_timeframe.setdefault(key, [])
        price_history.append(float(bar.close))
        result = engine.analyze_symbol(symbol, tuple(price_history))
        context = result.to_dict()
        metadata = dict(bar.metadata or {})
        existing_regime = str(metadata.get("regime") or "").strip().lower()
        computed_regime = str(context.get("regime") or "unknown")
        if existing_regime in {"", "unknown", "none", "null"}:
            metadata["regime"] = computed_regime
        metadata["regime_context"] = context
        metadata["regime_source"] = "research_regime_features"
        metadata["regime_segmentation"] = {
            "segmentation_id": segmentation.segmentation_id,
            "segmentation_version": segmentation.version,
            "segmentation_fingerprint": segmentation.fingerprint,
            "feature_config_fingerprint": config_fingerprint,
            "trial_id": trial["trial_id"] if trial is not None else None,
            "baseline": not custom_context,
            "research_only": True,
        }
        enriched.append(replace(bar, metadata=metadata))

    return enriched

