from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.regime_features import RegimeFeatureConfig, RegimeFeatureEngine
from autobot.v2.research.market_data_repository import MarketBar
from autobot.v2.research.regime_context import enrich_bars_with_regime_context


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

