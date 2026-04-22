import concurrent.futures

import pytest

from autobot.v2.reports import DailyReporter


pytestmark = pytest.mark.unit


def _sample_trades():
    return [
        {
            "pair": "BTC/USD",
            "side": "sell",
            "profit": 25.50,
            "volume": 0.001,
            "price": 50000.0,
            "instance_id": "test-1",
        },
        {
            "pair": "BTC/USD",
            "side": "sell",
            "profit": -10.00,
            "volume": 0.001,
            "price": 49500.0,
            "instance_id": "test-1",
        },
        {
            "pair": "ETH/USD",
            "side": "sell",
            "profit": 15.00,
            "volume": 0.1,
            "price": 3000.0,
            "instance_id": "test-2",
        },
        {
            "pair": "ETH/USD",
            "side": "sell",
            "profit": 5.00,
            "volume": 0.05,
            "price": 3100.0,
            "instance_id": "test-2",
        },
    ]


def test_daily_reporter_generate_report_schema_and_metrics_are_stable():
    reporter = DailyReporter(orchestrator=None)
    for trade in _sample_trades():
        reporter.record_trade(trade)

    report = reporter.generate_report()

    assert report["total_trades"] == 4
    assert abs(report["total_profit"] - 35.50) < 0.01
    assert report["win_count"] == 3
    assert report["loss_count"] == 1
    assert abs(report["win_rate"] - 75.0) < 0.1
    assert abs(report["profit_factor"] - 4.55) < 0.01

    expected_keys = {
        "date",
        "generated_at",
        "total_trades",
        "total_profit",
        "win_count",
        "loss_count",
        "win_rate",
        "profit_factor",
        "gross_profit",
        "gross_loss",
        "pairs",
        "human_summary",
    }
    assert expected_keys.issubset(report.keys())
    assert set(report["pairs"].keys()) == {"BTC/USD", "ETH/USD"}
    assert report["pairs"]["BTC/USD"]["trades"] == 2
    assert report["pairs"]["ETH/USD"]["trades"] == 2
    assert report["human_summary"]


def test_daily_reporter_empty_report_schema_is_unambiguous():
    report = DailyReporter(orchestrator=None).generate_report()

    expected_keys = {
        "date",
        "generated_at",
        "total_trades",
        "total_profit",
        "win_count",
        "loss_count",
        "win_rate",
        "profit_factor",
        "gross_profit",
        "gross_loss",
        "pairs",
        "human_summary",
    }
    assert set(report.keys()) == expected_keys
    assert report["total_trades"] == 0
    assert report["pairs"] == {}
    assert "Aucun trade" in report["human_summary"]


def test_daily_reporter_thread_safety_records_all_trades():
    reporter = DailyReporter(orchestrator=None)

    def record_many(n: int) -> int:
        for i in range(n):
            reporter.record_trade(
                {
                    "pair": "BTC/USD",
                    "side": "sell",
                    "profit": 1.0,
                    "volume": 0.001,
                    "price": 50000.0,
                    "instance_id": f"t-{i}",
                }
            )
        return n

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(record_many, 100) for _ in range(4)]
        for future in futures:
            assert future.result() == 100

    assert len(reporter._daily_trades) == 400


def test_daily_reporter_start_stop_scheduler_lifecycle():
    reporter = DailyReporter(orchestrator=None)
    reporter.start()
    assert reporter._thread is not None and reporter._thread.is_alive()
    reporter.stop()
    assert reporter._thread is not None and not reporter._thread.is_alive()
