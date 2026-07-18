from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.contracts import MarketIdentity
from autobot.v2.research.feature_registry import (
    DATA_MISSING,
    READY,
    WAITING_FOR_MORE_DATA,
    FeatureDefinition,
    FeatureRegistry,
    default_feature_registry,
    validate_historical_shadow_parity,
)


pytestmark = pytest.mark.unit


def _market() -> MarketIdentity:
    return MarketIdentity(exchange="kraken", market_type="spot", symbol="BTCZEUR", base_asset="BTC", quote_asset="EUR")


def _rows() -> list[dict[str, str]]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[dict[str, str]] = []
    for index, close in enumerate((100.0, 101.0, 103.0, 104.0, 105.0)):
        event_time = start + timedelta(minutes=5 * index)
        rows.append(
            {
                "event_time": event_time.isoformat(),
                "available_time": (event_time + timedelta(minutes=5)).isoformat(),
                "bar_close_time": (event_time + timedelta(minutes=5)).isoformat(),
                "open": str(close - 0.5),
                "high": str(close + 1.0),
                "low": str(close - 1.0),
                "close": str(close),
                "volume": "100",
            }
        )
    return rows


def test_feature_registry_uses_only_closed_bars_and_waits_for_lookback():
    registry = FeatureRegistry((FeatureDefinition("return_1", "1", "canonical_ohlcv", "return_bps"),))
    values = registry.compute_series(
        rows=_rows(),
        market=_market(),
        timeframe="5m",
        source_snapshot_id="snapshot-1",
    )

    assert values[0].status == WAITING_FOR_MORE_DATA
    assert values[1].status == READY
    assert float(values[1].value) == pytest.approx(100.0)
    assert values[1].event_time == datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc)
    assert values[1].available_time == datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc)


def test_feature_registry_iterator_matches_materialized_series():
    registry = default_feature_registry()
    kwargs = {
        "rows": _rows(),
        "market": _market(),
        "timeframe": "5m",
        "source_snapshot_id": "snapshot-iterator",
        "feature_ids": ("return_1_bps", "momentum_3_bps"),
    }

    assert tuple(registry.iter_series(**kwargs)) == registry.compute_series(**kwargs)


def test_feature_registry_rejects_unverified_basis_and_keeps_missing_separate():
    registry = FeatureRegistry((FeatureDefinition("basis", "1", "basis", "basis_bps"),))
    row = {
        "event_time": "2026-01-01T00:00:00+00:00",
        "available_time": "2026-01-01T00:00:00+00:00",
        "basis_bps": "120",
        "confidence_status": "BASIS_REFERENCE_UNVERIFIED",
    }

    value = registry.compute_series(
        rows=(row,),
        market=_market(),
        timeframe="1m",
        source_snapshot_id="basis-snapshot",
    )[0]

    assert value.status == DATA_MISSING
    assert value.value is None
    assert value.metadata["reason"] == "basis_reference_unverified"


def test_feature_registry_historical_shadow_parity_is_deterministic():
    result = validate_historical_shadow_parity(
        rows=_rows(),
        market=_market(),
        timeframe="5m",
        source_snapshot_id="snapshot-parity",
        registry=default_feature_registry(),
        feature_ids=("return_1_bps", "momentum_3_bps", "atr_14_bps"),
    )

    assert result.parity_ok is True
    assert result.feature_count == 15
    assert result.differences == ()


def test_feature_registry_delays_visibility_until_ingestion_and_replays_identically():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        {
            "event_time": start.isoformat(),
            "available_time": (start + timedelta(minutes=5)).isoformat(),
            "ingestion_time": (start + timedelta(minutes=15)).isoformat(),
            "close": "100",
        },
        {
            "event_time": (start + timedelta(minutes=5)).isoformat(),
            "available_time": (start + timedelta(minutes=10)).isoformat(),
            "ingestion_time": (start + timedelta(minutes=10)).isoformat(),
            "close": "101",
        },
    ]
    registry = FeatureRegistry((FeatureDefinition("return_1", "1", "canonical_ohlcv", "return_bps"),))

    values = registry.compute_series(
        rows=rows,
        market=_market(),
        timeframe="5m",
        source_snapshot_id="delayed-ingestion",
    )
    second_bar = next(item for item in values if item.event_time == start + timedelta(minutes=5))
    parity = validate_historical_shadow_parity(
        rows=rows,
        market=_market(),
        timeframe="5m",
        source_snapshot_id="delayed-ingestion",
        registry=registry,
    )

    assert second_bar.status == WAITING_FOR_MORE_DATA
    assert second_bar.available_time == start + timedelta(minutes=10)
    assert parity.parity_ok is True


def test_feature_registry_rejects_naive_temporal_rows():
    registry = default_feature_registry()
    with pytest.raises(ValueError, match="timezone-aware"):
        registry.compute_series(
            rows=({"event_time": "2026-01-01T00:00:00", "available_time": "2026-01-01T00:05:00", "close": "100"},),
            market=_market(),
            timeframe="5m",
            source_snapshot_id="bad-time",
            feature_ids=("return_1_bps",),
        )


def test_feature_registry_uses_bounded_history_for_monotonic_canonical_rows():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(2_000):
        event_time = start + timedelta(minutes=5 * index)
        rows.append(
            {
                "event_time": event_time.isoformat(),
                "available_time": (event_time + timedelta(minutes=5)).isoformat(),
                "open": "100",
                "high": "102",
                "low": "99",
                "close": str(100 + index),
                "volume": "100",
            }
        )

    values = default_feature_registry().compute_series(
        rows=rows,
        market=_market(),
        timeframe="5m",
        source_snapshot_id="long-canonical-snapshot",
        feature_ids=("momentum_3_bps", "atr_14_bps"),
    )

    assert len(values) == 4_000
    assert values[-1].status == READY
    assert float(values[-2].value) == pytest.approx(((2099 / 2096) - 1.0) * 10_000.0)
