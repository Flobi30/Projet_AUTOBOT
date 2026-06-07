from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research.data_readiness_dashboard import (
    build_data_readiness_dashboard,
    write_data_readiness_dashboard,
)


pytestmark = pytest.mark.unit


def _write_short_ohlcv(path):
    start = datetime(2026, 6, 7, tzinfo=timezone.utc)
    lines = ["timestamp,symbol,timeframe,open,high,low,close,volume"]
    for idx in range(12):
        ts = start + timedelta(minutes=5 * idx)
        lines.append(f"{ts.isoformat()},TRXEUR,5m,100,101,99,100.5,1000")
    path.write_text("\n".join(lines), encoding="utf-8")


def test_data_readiness_blocks_short_history_and_missing_microstructure(tmp_path):
    csv_path = tmp_path / "short_trx_5m.csv"
    _write_short_ohlcv(csv_path)

    report = build_data_readiness_dashboard(
        run_id="pytest_readiness",
        dataset_paths=(csv_path,),
        default_timeframe="5m",
    )
    written = write_data_readiness_dashboard(report, tmp_path / "reports")

    row = written.rows[0]
    assert row.symbol == "TRXEUR"
    assert row.timeframe == "5m"
    assert row.bar_count == 12
    assert row.gap_count == 0
    assert row.duplicate_count_final == 0
    assert row.batch_validation_ready is False
    assert row.paper_candidate_review_ready is False
    assert row.microstructure_status == "missing"
    assert row.live_promotion_allowed is False
    assert row.usability_tier == "not_ready_for_cost_sensitive_intraday"
    assert written.markdown_report_path
    assert "No paper or live order is created." in written.safety_notes
