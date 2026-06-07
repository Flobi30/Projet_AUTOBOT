from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research.data_quality_report import analyze_bars, build_data_foundation_readiness_report
from autobot.v2.research.market_data_repository import MarketBar


pytestmark = pytest.mark.unit


def _bar(ts, *, timeframe="5m", metadata=None):
    return MarketBar(
        timestamp=ts,
        symbol="TRXEUR",
        timeframe=timeframe,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=100.0,
        metadata=metadata or {},
    )


def test_short_clean_ohlcv_without_book_is_not_ready_for_cost_sensitive_intraday():
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    bars = [_bar(start + timedelta(minutes=5 * idx)) for idx in range(12)]

    report = analyze_bars(
        bars,
        source_path="memory://short",
        source_type="unit",
        expected_interval_seconds=300,
    )

    assert report.usable_for_backtest is True
    assert report.duplicate_count == 0
    assert report.final_usability_tier == "not_ready_for_cost_sensitive_intraday"
    assert report.bid_ask_coverage == pytest.approx(0.0)
    assert report.depth_coverage == pytest.approx(0.0)


def test_long_clean_ohlcv_with_book_is_ready_for_paper_candidate_review():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    metadata = {"best_bid": 99.9, "best_ask": 100.1, "depth_eur": 10_000.0}
    bars = [_bar(start + timedelta(hours=idx), timeframe="1h", metadata=metadata) for idx in range(365 * 24 + 1)]

    file_report = analyze_bars(
        bars,
        source_path="memory://long",
        source_type="unit",
        expected_interval_seconds=3600,
    )
    readiness = build_data_foundation_readiness_report(
        run_id="pytest_tiers",
        file_reports=(file_report,),
    )

    assert file_report.coverage_days >= 365.0
    assert file_report.final_usability_tier == "ready_for_paper_candidate_review"
    assert readiness.overall_status == "ready_for_paper_candidate_review"
    assert readiness.status_tiers == ("ready_for_paper_candidate_review",)
