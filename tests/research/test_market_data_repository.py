from datetime import datetime, timezone

import pytest

from autobot.v2.research.market_data_repository import MarketBar, MarketDataRepository


pytestmark = pytest.mark.unit


def test_market_data_repository_loads_sorts_and_validates_csv(tmp_path):
    csv_path = tmp_path / "bars.csv"
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,symbol,timeframe,open,high,low,close,volume",
                "2026-05-31T00:01:00+00:00,TRXEUR,1m,1.0,1.2,0.9,1.1,100",
                "2026-05-31T00:00:00+00:00,TRXEUR,1m,1.0,1.1,0.9,1.0,90",
            ]
        ),
        encoding="utf-8",
    )

    repository = MarketDataRepository()
    bars = repository.load_csv(csv_path)
    report = repository.validate(bars, expected_interval_seconds=60)

    assert [bar.timestamp.minute for bar in bars] == [0, 1]
    assert report.ok is True
    assert report.symbols == ("TRXEUR",)
    assert report.row_count == 2


def test_market_data_repository_detects_duplicates_and_gaps():
    repository = MarketDataRepository()
    first = MarketBar(
        timestamp=datetime(2026, 5, 31, 0, 0, tzinfo=timezone.utc),
        symbol="XXBTZEUR",
        timeframe="1m",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
    )
    duplicate = MarketBar(
        timestamp=first.timestamp,
        symbol="XXBTZEUR",
        timeframe="1m",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
    )
    later = MarketBar(
        timestamp=datetime(2026, 5, 31, 0, 10, tzinfo=timezone.utc),
        symbol="XXBTZEUR",
        timeframe="1m",
        open=102.0,
        high=103.0,
        low=101.0,
        close=102.5,
        volume=8.0,
    )

    report = repository.validate([first, duplicate, later], expected_interval_seconds=60)

    assert report.ok is False
    assert report.duplicate_count == 1
    assert report.gap_count == 1
    assert "duplicate_bars" in report.warnings


def test_market_bar_rejects_impossible_ohlc():
    with pytest.raises(ValueError, match="high"):
        MarketBar.from_mapping(
            {
                "timestamp": "2026-05-31T00:00:00+00:00",
                "symbol": "TRXEUR",
                "timeframe": "1m",
                "open": 10,
                "high": 9,
                "low": 8,
                "close": 10,
                "volume": 1,
            }
        )
