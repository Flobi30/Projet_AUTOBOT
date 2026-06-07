import csv

import pytest

from autobot.v2.research.microstructure_profile import (
    build_microstructure_profile,
    write_microstructure_profile_report,
)


pytestmark = pytest.mark.unit


def test_microstructure_profile_calculates_spread_and_depth_quantiles(tmp_path):
    csv_path = tmp_path / "spread_depth.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "timestamp_local",
                "timestamp_exchange",
                "symbol",
                "source",
                "best_bid",
                "best_ask",
                "mid_price",
                "spread_bps",
                "bid_depth_eur",
                "ask_depth_eur",
                "latency_ms",
            ],
        )
        writer.writeheader()
        for spread, bid_depth, ask_depth, latency in [
            (1.0, 1000.0, 900.0, 10.0),
            (2.0, 1100.0, 950.0, 20.0),
            (3.0, 1200.0, 1000.0, 30.0),
            (4.0, 1300.0, 1050.0, 40.0),
            (5.0, 1400.0, 1100.0, 50.0),
        ]:
            writer.writerow(
                {
                    "timestamp_local": "2026-06-07T00:00:00+00:00",
                    "timestamp_exchange": "2026-06-07T00:00:00+00:00",
                    "symbol": "TRXEUR",
                    "source": "kraken_rest_public_depth",
                    "best_bid": 100.0,
                    "best_ask": 100.1,
                    "mid_price": 100.05,
                    "spread_bps": spread,
                    "bid_depth_eur": bid_depth,
                    "ask_depth_eur": ask_depth,
                    "latency_ms": latency,
                }
            )

    report = build_microstructure_profile((csv_path,), run_id="pytest_micro_profile")
    written = write_microstructure_profile_report(report, tmp_path / "reports")

    profile = written.profiles[0]
    assert profile.symbol == "TRXEUR"
    assert profile.sample_count == 5
    assert profile.p95_spread_bps == pytest.approx(5.0)
    assert profile.median_bid_depth_eur == pytest.approx(1200.0)
    assert profile.median_ask_depth_eur == pytest.approx(1000.0)
    assert profile.p95_latency_ms == pytest.approx(50.0)
    assert profile.cost_risk_status == "cheap"
    assert profile.recommended_research_spread_bps == pytest.approx(4.0)
    assert profile.recommended_stress_spread_bps == pytest.approx(5.0)
    assert written.json_report_path
    assert written.markdown_report_path
    assert "No paper or live order is created." in written.safety_notes
