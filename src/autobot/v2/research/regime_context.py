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
from typing import Sequence

from autobot.v2.regime_features import RegimeFeatureEngine

from .market_data_repository import MarketBar, MarketDataRepository


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


def record_regime_segmentation_trial(
    *,
    path: str | Path,
    segmentation: BoundedRegimeSegmentation,
    snapshot_id: str,
    outcome: str = "PENDING",
) -> dict[str, str]:
    """Append an idempotent research trial record without touching runtime."""

    trial = {
        "trial_id": f"regime_{segmentation.fingerprint[:16]}_{snapshot_id}",
        "segmentation_id": segmentation.segmentation_id,
        "segmentation_version": segmentation.version,
        "segmentation_fingerprint": segmentation.fingerprint,
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


def enrich_bars_with_regime_context(
    bars: Sequence[MarketBar],
    *,
    regime_engine: RegimeFeatureEngine | None = None,
) -> list[MarketBar]:
    """Return bars enriched with regime metadata from observed history only."""

    engine = regime_engine or RegimeFeatureEngine()
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
        enriched.append(replace(bar, metadata=metadata))

    return enriched

