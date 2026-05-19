from autobot.v2.setup_optimizer import PairSetupOptimizer, SetupOptimizerConfig

import pytest


pytestmark = pytest.mark.unit


def _optimizer() -> PairSetupOptimizer:
    return PairSetupOptimizer(
        SetupOptimizerConfig(
            min_closed_trades=30,
            candidate_profit_factor=1.25,
            strong_profit_factor=1.60,
            min_net_pnl_eur=0.0,
            candidate_score=70.0,
        )
    )


def test_setup_optimizer_uses_fallback_for_future_pairs():
    snapshot = _optimizer().build_snapshot(
        instances=[{"id": "inst-new", "symbol": "NEWEUR", "strategy": "grid"}],
        opportunities=[
            {
                "symbol": "NEWEUR",
                "score": 55.0,
                "status": "non_tradable",
                "reason": "no_recent_signal",
                "cost_bps": 16.0,
                "regime_context": {"regime": "range", "confidence": 0.62},
            }
        ],
        health_by_symbol={},
        paper_mode=True,
        total_capital=800.0,
    )

    assert snapshot["paper_mode"] is True
    assert snapshot["live_promotion_allowed"] is False
    assert snapshot["setups"][0]["symbol"] == "NEWEUR"
    assert snapshot["setups"][0]["current_context"]["profile_source"] == "fallback_profile"
    assert snapshot["setups"][0]["selected_variant"]["name"] in {
        "grid_balanced",
        "grid_tight_range",
        "grid_defensive_observe",
    }


def test_setup_optimizer_promotes_positive_range_setup_for_review_only():
    snapshot = _optimizer().build_snapshot(
        instances=[{"id": "inst-trx", "symbol": "TRXEUR", "strategy": "grid"}],
        opportunities=[
            {
                "symbol": "TRXEUR",
                "score": 72.0,
                "status": "non_tradable",
                "reason": "no_recent_signal",
                "cost_bps": 16.0,
                "regime_context": {"regime": "range", "confidence": 0.75},
            }
        ],
        health_by_symbol={
            "TRXEUR": {
                "symbol": "TRXEUR",
                "status": "healthy",
                "closed_trades": 42,
                "net_pnl_eur": 1.14,
                "profit_factor": 1.73,
                "win_rate": 69.0,
            }
        },
        paper_mode=True,
        total_capital=800.0,
    )

    row = snapshot["setups"][0]
    assert row["status"] == "candidate"
    assert row["recommended_action"] == "paper_review_selected_variant"
    assert row["execution_policy"]["live_promotion_allowed"] is False
    assert row["selected_variant"]["status"] == "candidate"


def test_setup_optimizer_routes_underperforming_high_vol_setup_to_paper_adjustment():
    snapshot = _optimizer().build_snapshot(
        instances=[{"id": "inst-eth", "symbol": "XETHZEUR", "strategy": "grid"}],
        opportunities=[
            {
                "symbol": "XETHZEUR",
                "score": 60.0,
                "status": "non_tradable",
                "reason": "pair_health_underperforming",
                "cost_bps": 16.0,
                "regime_context": {"regime": "high_vol", "confidence": 0.67},
            }
        ],
        health_by_symbol={
            "XETHZEUR": {
                "symbol": "XETHZEUR",
                "status": "underperforming",
                "closed_trades": 41,
                "net_pnl_eur": -3.07,
                "profit_factor": 0.10,
                "win_rate": 12.2,
            }
        },
        paper_mode=True,
        total_capital=800.0,
    )

    row = snapshot["setups"][0]
    assert row["status"] == "pause_current"
    assert row["recommended_action"] == "pause_current_setup_and_test_selected_variant_in_paper"
    assert row["selected_variant"]["name"] in {"grid_volatility", "grid_wide", "grid_defensive_observe"}
    assert row["execution_policy"]["paper_only"] is True
