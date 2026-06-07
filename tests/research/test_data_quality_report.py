from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research.data_quality_report import (
    analyze_bars,
    analyze_dataset_files,
    build_data_foundation_readiness_report,
    write_data_foundation_readiness_report,
)
from autobot.v2.research.market_data_repository import MarketBar


pytestmark = pytest.mark.unit


def _bar(ts, *, close=100.0, volume=0.0, metadata=None):
    return MarketBar(
        timestamp=ts,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=volume,
        symbol="TRXEUR",
        timeframe="5m",
        metadata=metadata or {},
    )


def test_data_quality_flags_gaps_missing_volume_and_missing_book_data():
    start = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
    bars = [
        _bar(start, volume=0.0),
        _bar(start + timedelta(minutes=5), volume=0.0),
        _bar(start + timedelta(minutes=20), volume=0.0),
    ]

    report = analyze_bars(
        bars,
        source_path="memory://pytest",
        source_type="unit",
        expected_interval_seconds=300,
    )

    assert report.row_count == 3
    assert report.gap_count == 1
    assert report.volume_status == "absent_or_zero"
    assert "volume_absent" in report.warnings
    assert "bid_ask_absent" in report.warnings
    assert "order_book_depth_absent" in report.warnings
    assert report.usable_for_backtest is False


def test_data_quality_marks_volume_and_book_present_when_metadata_exists():
    start = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
    bars = [
        _bar(start, volume=100.0, metadata={"bid": 99.9, "ask": 100.1, "depth_eur": 5000.0}),
        _bar(start + timedelta(minutes=5), volume=120.0, metadata={"bid": 100.0, "ask": 100.2, "depth_eur": 6000.0}),
    ]

    report = analyze_bars(
        bars,
        source_path="memory://pytest",
        source_type="unit",
        expected_interval_seconds=300,
    )

    assert report.volume_status == "present"
    assert report.has_bid_ask is True
    assert report.has_depth is True
    assert report.usable_for_backtest is True


def test_data_foundation_report_writer_outputs_json_and_markdown(tmp_path):
    csv_path = tmp_path / "bars.csv"
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,symbol,timeframe,open,high,low,close,volume",
                "2026-06-01T00:00:00+00:00,TRXEUR,5m,100,101,99,100,100",
                "2026-06-01T00:05:00+00:00,TRXEUR,5m,100,102,99,101,120",
            ]
        ),
        encoding="utf-8",
    )

    file_reports = analyze_dataset_files((csv_path,), default_timeframe="5m")
    report = build_data_foundation_readiness_report(
        run_id="pytest_data_foundation",
        file_reports=file_reports,
    )
    written = write_data_foundation_readiness_report(report, tmp_path / "reports")

    assert written.json_report_path
    assert written.markdown_report_path
    assert written.overall_status in {
        "ready_for_ohlcv_research",
        "not_ready_for_cost_sensitive_intraday",
        "ready_for_batch_validation",
        "ready_for_paper_candidate_review",
        "partial",
        "not_ready",
    }
    markdown = (tmp_path / "reports" / "pytest_data_foundation.md").read_text(encoding="utf-8")
    assert "Data Foundation Readiness" in markdown
    assert "No paper or live order is created." in markdown
