"""Research-only market-regime enrichment for validation replays.

The helpers in this module attach Markov/entropy regime context to replay
``MarketBar`` objects without touching runtime paper/live execution. Enrichment
is chronological per symbol, so a bar never receives information from future
bars.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from autobot.v2.regime_features import RegimeFeatureEngine

from .market_data_repository import MarketBar, MarketDataRepository


def enrich_bars_with_regime_context(
    bars: Sequence[MarketBar],
    *,
    regime_engine: RegimeFeatureEngine | None = None,
) -> list[MarketBar]:
    """Return bars enriched with regime metadata from observed history only."""

    engine = regime_engine or RegimeFeatureEngine()
    repository = MarketDataRepository()
    ordered_bars = repository.normalize(bars)
    history_by_symbol: dict[str, list[float]] = {}
    enriched: list[MarketBar] = []

    for bar in ordered_bars:
        symbol = bar.symbol.upper()
        price_history = history_by_symbol.setdefault(symbol, [])
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

