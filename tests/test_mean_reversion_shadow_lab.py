import json
import sqlite3

import pytest

from autobot.v2.mean_reversion_shadow_lab import (
    MeanReversionShadowConfig,
    MeanReversionShadowLab,
    MeanReversionVariant,
)


pytestmark = pytest.mark.unit


def _variant() -> MeanReversionVariant:
    return MeanReversionVariant(
        name="mr_test_snapback",
        description="Small-window test mean-reversion",
        window=5,
        entry_z=1.0,
        exit_z=0.15,
        stop_z=4.0,
        atr_window=2,
        min_bandwidth_bps=0.1,
        max_bandwidth_bps=5000.0,
        max_abs_trend_bps=2500.0,
        min_atr_bps=0.1,
        max_atr_bps=5000.0,
        min_expected_net_edge_bps=0.0,
        position_pct=0.50,
        cooldown_ticks=0,
    )


def _lab(tmp_path) -> MeanReversionShadowLab:
    return MeanReversionShadowLab(
        MeanReversionShadowConfig(
            db_path=str(tmp_path / "mean_reversion_shadow_lab.db"),
            virtual_capital_per_variant=100.0,
            min_tick_seconds=0,
            persist_interval_seconds=1,
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
            min_samples_for_signal=5,
            min_closed_trades_for_signal=1,
            candidate_score=50.0,
            candidate_profit_factor=1.0,
        ),
        variants=[_variant()],
    )


def test_mean_reversion_shadow_lab_opens_and_closes_snapback(tmp_path):
    lab = _lab(tmp_path)
    prices = [100.0, 101.0, 99.0, 100.0, 100.0, 90.0, 95.0, 99.0]

    for idx, price in enumerate(prices):
        lab.on_price_tick(symbol="NEWEUR", price=price, timestamp=f"2026-05-20T01:0{idx}:00+00:00")
    lab.flush()

    snapshot = lab.build_snapshot(symbols=["NEWEUR"])
    assert snapshot["paper_only"] is True
    assert snapshot["writes_official_paper_ledger"] is False
    assert snapshot["engine"] == "mean_reversion"
    best = snapshot["by_symbol"]["NEWEUR"]["best_variant"]
    assert best["closed_trades"] >= 1
    assert best["net_pnl_eur"] > 0
    assert best["evidence_source"] == "mean_reversion_shadow_lab"

    reloaded = MeanReversionShadowLab(lab.config, variants=[_variant()])
    reloaded_snapshot = reloaded.build_snapshot(symbols=["NEWEUR"])
    assert reloaded_snapshot["by_symbol"]["NEWEUR"]["best_variant"]["closed_trades"] >= 1


def test_mean_reversion_shadow_lab_persists_opportunity_score_on_closed_trade(tmp_path):
    lab = _lab(tmp_path)
    prices = [100.0, 101.0, 99.0, 100.0, 100.0, 90.0, 95.0, 99.0]
    opportunity = {
        "score": 43.5,
        "status": "non_tradable",
        "reason": "score_below_threshold",
        "components": {"spread": 0.4},
    }

    for idx, price in enumerate(prices):
        lab.on_price_tick(
            symbol="SCOREEUR",
            price=price,
            timestamp=f"2026-05-20T01:3{idx}:00+00:00",
            opportunity_context=opportunity,
        )
    lab.flush()

    with sqlite3.connect(lab.config.db_path) as conn:
        row = conn.execute(
            """
            SELECT opportunity_score, opportunity_status, opportunity_reason, opportunity_components
            FROM mean_reversion_shadow_trades
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    assert row[0] == pytest.approx(43.5)
    assert row[1] == "non_tradable"
    assert row[2] == "score_below_threshold"
    assert json.loads(row[3]) == {"spread": 0.4}


def test_mean_reversion_shadow_lab_persists_entry_features_on_closed_trade(tmp_path):
    lab = _lab(tmp_path)
    prices = [100.0, 101.0, 99.0, 100.0, 100.0, 90.0, 95.0, 99.0]

    for idx, price in enumerate(prices):
        lab.on_price_tick(symbol="FEATUREEUR", price=price, timestamp=f"2026-05-20T01:4{idx}:00+00:00")
    lab.flush()

    with sqlite3.connect(lab.config.db_path) as conn:
        row = conn.execute(
            """
            SELECT entry_features_json
            FROM mean_reversion_shadow_trades
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    features = json.loads(row[0])
    assert features["ready"] is True
    assert features["expected_gross_edge_bps"] > 0
    assert "realized_pnl" not in features
    assert "net_pnl" not in features


def test_mean_reversion_shadow_lab_rejects_strong_trend(tmp_path):
    lab = _lab(tmp_path)
    trend_variant = MeanReversionVariant(
        name="mr_trend_reject",
        description="Reject strong trend",
        window=5,
        entry_z=0.5,
        atr_window=2,
        min_bandwidth_bps=0.1,
        max_bandwidth_bps=5000.0,
        max_abs_trend_bps=50.0,
        min_atr_bps=0.1,
        max_atr_bps=5000.0,
        min_expected_net_edge_bps=0.0,
    )
    lab = MeanReversionShadowLab(lab.config, variants=[trend_variant])
    for idx, price in enumerate([100.0, 99.0, 98.0, 97.0, 90.0, 89.0]):
        lab.on_price_tick(symbol="TRENDEUR", price=price, timestamp=f"2026-05-20T01:1{idx}:00+00:00")

    snapshot = lab.build_snapshot(symbols=["TRENDEUR"])
    best = snapshot["by_symbol"]["TRENDEUR"]["best_variant"]
    assert best["opened_trades"] == 0
    assert best["last_decision"]["reason"] == "trend_too_strong_for_mean_reversion"


def test_mean_reversion_shadow_lab_rejects_when_expected_edge_below_cost(tmp_path):
    expensive_variant = MeanReversionVariant(
        name="mr_cost_guard",
        description="Reject weak snapback after estimated costs",
        window=5,
        entry_z=0.25,
        atr_window=2,
        min_bandwidth_bps=0.1,
        max_bandwidth_bps=5000.0,
        max_abs_trend_bps=2500.0,
        min_atr_bps=0.1,
        max_atr_bps=5000.0,
        min_expected_net_edge_bps=20.0,
    )
    lab = MeanReversionShadowLab(
        MeanReversionShadowConfig(
            db_path=str(tmp_path / "mean_reversion_shadow_lab.db"),
            virtual_capital_per_variant=100.0,
            min_tick_seconds=0,
            min_samples_for_signal=5,
            fee_bps_per_side=12.0,
            slippage_bps_per_side=3.0,
        ),
        variants=[expensive_variant],
    )
    for idx, price in enumerate([100.0, 100.2, 99.8, 100.1, 99.9, 99.7]):
        lab.on_price_tick(symbol="COSTEUR", price=price, timestamp=f"2026-05-20T01:2{idx}:00+00:00")

    snapshot = lab.build_snapshot(symbols=["COSTEUR"])
    best = snapshot["by_symbol"]["COSTEUR"]["best_variant"]
    assert best["opened_trades"] == 0
    assert best["last_decision"]["reason"] == "expected_edge_below_cost"


def test_mean_reversion_shadow_lab_learning_status_with_short_history(tmp_path):
    lab = _lab(tmp_path)
    lab.on_price_tick(symbol="LEARNEUR", price=100.0, timestamp="2026-05-20T01:00:00+00:00")
    lab.on_price_tick(symbol="LEARNEUR", price=90.0, timestamp="2026-05-20T01:01:00+00:00")

    snapshot = lab.build_snapshot(symbols=["LEARNEUR"])
    best = snapshot["by_symbol"]["LEARNEUR"]["best_variant"]
    assert best["status"] == "learning"
    assert best["closed_trades"] == 0
