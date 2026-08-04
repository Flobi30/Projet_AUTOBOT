from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research.market_data_repository import MarketBar
from autobot.v2.research.oos_benchmarks import evaluate_closed_oos_trade_benchmarks
from autobot.v2.research.trade_journal import TradeRecord


pytestmark = pytest.mark.unit


def _bar(index: int, price: float, *, symbol: str = "BTCEUR") -> MarketBar:
    timestamp = datetime(2026, 7, 1, tzinfo=timezone.utc) + timedelta(hours=index)
    return MarketBar(
        timestamp=timestamp,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=1_000.0,
        symbol=symbol,
        timeframe="1h",
    )


def _trade(
    *,
    opened_index: int,
    closed_index: int,
    entry: float,
    exit_price: float,
    notional: float = 100.0,
    cost: float = 0.50,
    symbol: str = "BTCEUR",
) -> TradeRecord:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    quantity = notional / entry
    gross = notional * ((exit_price / entry) - 1.0)
    return TradeRecord(
        run_id="pytest_oos_benchmark",
        strategy_id="funding_basis",
        symbol=symbol,
        side="buy",
        opened_at=start + timedelta(hours=opened_index),
        closed_at=start + timedelta(hours=closed_index),
        quantity=quantity,
        entry_price=entry,
        exit_price=exit_price,
        gross_pnl_eur=gross,
        net_pnl_eur=gross - cost,
        fees_eur=cost,
    )


def test_oos_benchmarks_are_deterministic_and_preserve_placebo_frequency():
    bars = tuple(_bar(index, price) for index, price in enumerate((100, 101, 102, 103, 104, 105, 106)))
    trades = (
        _trade(opened_index=1, closed_index=2, entry=101, exit_price=102),
        _trade(opened_index=3, closed_index=4, entry=103, exit_price=104),
    )

    first = evaluate_closed_oos_trade_benchmarks(trades, bars, timeframe="1h", seed_salt="fixed")
    second = evaluate_closed_oos_trade_benchmarks(tuple(reversed(trades)), bars, timeframe="1h", seed_salt="fixed")

    assert first.to_dict() == second.to_dict()
    assert first.status == "READY"
    assert first.strategy_trade_count == 2
    assert {baseline.name for baseline in first.baselines} == {
        "no_trade",
        "buy_and_hold_oos_window",
        "placebo_same_frequency",
    }
    placebo = next(baseline for baseline in first.baselines if baseline.name == "placebo_same_frequency")
    assert placebo.trade_count == first.strategy_trade_count
    assert placebo.deployed_notional_eur == pytest.approx(200.0)
    assert first.paper_capital_allowed is False
    assert first.live_allowed is False
    assert first.promotable is False


def test_oos_benchmarks_fail_closed_when_one_candidate_symbol_lacks_closed_oos_bars():
    bars = tuple(_bar(index, price) for index, price in enumerate((100, 101, 102, 103)))
    trade = _trade(opened_index=1, closed_index=2, entry=101, exit_price=102, symbol="ETHEUR")

    report = evaluate_closed_oos_trade_benchmarks((trade,), bars, timeframe="1h", seed_salt="fixed")

    assert report.status == "INSUFFICIENT_DATA"
    assert report.baselines == ()
    assert report.beats_all_baselines is None
    assert report.reasons == ("oos_bars_insufficient:ETHEUR",)


def test_oos_benchmarks_reject_unreproducible_candidate_pnl_before_comparing_references():
    bars = tuple(_bar(index, price) for index, price in enumerate((100, 101, 102, 103)))
    valid = _trade(opened_index=1, closed_index=2, entry=101, exit_price=102)
    tampered = TradeRecord(
        **{**valid.__dict__, "net_pnl_eur": valid.net_pnl_eur + 1.0}
    )

    report = evaluate_closed_oos_trade_benchmarks((tampered,), bars, timeframe="1h", seed_salt="fixed")

    assert report.status == "INSUFFICIENT_DATA"
    assert report.reasons == ("oos_trade_evidence_invalid:net_pnl_eur_not_reproducible_from_explicit_costs",)
