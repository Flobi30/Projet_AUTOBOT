import pytest

from autobot.v2.trend_shadow_lab import (
    TrendShadowLab,
    TrendShadowLabConfig,
    TrendShadowVariant,
)


pytestmark = pytest.mark.unit


def _variant() -> TrendShadowVariant:
    return TrendShadowVariant(
        name="trend_test_breakout",
        description="Small-window test breakout",
        kind="donchian",
        breakout_window=3,
        exit_window=2,
        momentum_window=2,
        atr_window=2,
        min_momentum_bps=5.0,
        min_atr_bps=0.1,
        max_atr_bps=2000.0,
        confirm_bps=0.0,
        trailing_atr_mult=8.0,
        stop_atr_mult=12.0,
        position_pct=0.50,
        cooldown_ticks=0,
    )


def _lab(tmp_path) -> TrendShadowLab:
    return TrendShadowLab(
        TrendShadowLabConfig(
            db_path=str(tmp_path / "trend_shadow_lab.db"),
            virtual_capital_per_variant=100.0,
            min_tick_seconds=0,
            persist_interval_seconds=1,
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
            min_samples_for_signal=4,
            min_closed_trades_for_signal=1,
            candidate_score=50.0,
            candidate_profit_factor=1.0,
        ),
        variants=[_variant()],
    )


def test_trend_shadow_lab_opens_and_closes_virtual_trend_trade(tmp_path):
    lab = _lab(tmp_path)
    prices = [100.0, 101.0, 102.0, 104.0, 108.0, 110.0, 107.0]

    for idx, price in enumerate(prices):
        lab.on_price_tick(symbol="NEWEUR", price=price, timestamp=f"2026-05-20T00:0{idx}:00+00:00")
    lab.flush()

    snapshot = lab.build_snapshot(symbols=["NEWEUR"])
    assert snapshot["paper_only"] is True
    assert snapshot["writes_official_paper_ledger"] is False
    assert snapshot["engine"] == "trend_momentum"
    row = snapshot["by_symbol"]["NEWEUR"]
    best = row["best_variant"]
    assert best["closed_trades"] >= 1
    assert best["net_pnl_eur"] > 0
    assert best["evidence_source"] == "trend_shadow_lab"

    reloaded = TrendShadowLab(lab.config, variants=[_variant()])
    reloaded_snapshot = reloaded.build_snapshot(symbols=["NEWEUR"])
    assert reloaded_snapshot["by_symbol"]["NEWEUR"]["best_variant"]["closed_trades"] >= 1


def test_trend_shadow_lab_does_not_trade_flat_market(tmp_path):
    lab = _lab(tmp_path)
    for idx, price in enumerate([100.0, 100.01, 100.0, 100.02, 100.01, 100.0, 100.01]):
        lab.on_price_tick(symbol="FLATEUR", price=price, timestamp=f"2026-05-20T00:1{idx}:00+00:00")

    snapshot = lab.build_snapshot(symbols=["FLATEUR"])
    best = snapshot["by_symbol"]["FLATEUR"]["best_variant"]
    assert best["opened_trades"] == 0
    assert best["last_decision"]["status"] == "rejected"
    assert best["last_decision"]["reason"] in {
        "atr_below_min",
        "momentum_below_min",
        "no_breakout",
        "warmup",
    }


def test_trend_shadow_lab_learning_status_with_short_history(tmp_path):
    lab = _lab(tmp_path)
    lab.on_price_tick(symbol="LEARNEUR", price=100.0, timestamp="2026-05-20T00:00:00+00:00")
    lab.on_price_tick(symbol="LEARNEUR", price=101.0, timestamp="2026-05-20T00:01:00+00:00")

    snapshot = lab.build_snapshot(symbols=["LEARNEUR"])
    best = snapshot["by_symbol"]["LEARNEUR"]["best_variant"]
    assert best["status"] == "learning"
    assert best["closed_trades"] == 0
