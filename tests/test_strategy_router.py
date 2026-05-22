import pytest

from autobot.v2.strategy_router import StrategyRouter, StrategyRouterConfig


pytestmark = pytest.mark.unit


def _router() -> StrategyRouter:
    return StrategyRouter(
        StrategyRouterConfig(
            min_shadow_closed_trades=3,
            candidate_score=70.0,
            watch_score=55.0,
            weak_score=40.0,
            no_trade_score=50.0,
            evidence_cap_learning_score=62.0,
        )
    )


def _symbol_payload(engine: str, variant: str, score: float, status: str, net: float, closed: int):
    return {
        "symbol": "NEWEUR",
        "engine": engine,
        "best_variant": {
            "symbol": "NEWEUR",
            "engine": engine,
            "variant": variant,
            "status": status,
            "score": score,
            "net_pnl_eur": net,
            "realized_pnl_eur": net,
            "profit_factor": 1.5 if net > 0 else 0.6,
            "win_rate": 60.0 if net > 0 else 35.0,
            "closed_trades": closed,
            "open_positions": 0,
            "sample_count": 100,
            "last_decision": {"status": "closed", "reason": "test"},
        },
    }


def test_strategy_router_selects_best_shadow_engine():
    snapshot = _router().build_snapshot(
        instances=[{"symbol": "NEWEUR"}],
        paper_mode=True,
        setup_shadow_by_symbol={
            "NEWEUR": _symbol_payload("dynamic_grid", "grid_wide", 52.0, "watch", 0.2, 4)
        },
        trend_shadow_by_symbol={
            "NEWEUR": _symbol_payload("trend_momentum", "trend_breakout", 82.0, "candidate", 3.0, 5)
        },
        mean_reversion_shadow_by_symbol={
            "NEWEUR": _symbol_payload("mean_reversion", "mr_balanced", 58.0, "watch", 0.3, 4)
        },
        opportunities=[],
    )

    row = snapshot["by_symbol"]["NEWEUR"]
    assert row["selected_engine"] == "trend_momentum"
    assert row["recommended_action"] == "shadow_candidate_review"
    assert row["live_promotion_allowed"] is False
    assert row["official_execution_enabled"] is True
    assert row["paper_execution_policy"]["support"] == "paper_official_candidate"
    assert snapshot["paper_official_execution_enabled"] is True


def test_strategy_router_marks_validated_grid_candidate_as_paper_official_candidate():
    snapshot = _router().build_snapshot(
        instances=[{"symbol": "NEWEUR"}],
        paper_mode=True,
        setup_shadow_by_symbol={
            "NEWEUR": _symbol_payload("dynamic_grid", "grid_tight_range", 82.0, "candidate", 3.0, 5)
        },
        opportunities=[],
    )

    row = snapshot["by_symbol"]["NEWEUR"]
    assert row["selected_engine"] == "dynamic_grid"
    assert row["recommended_action"] == "shadow_candidate_review"
    assert row["official_execution_enabled"] is True
    assert row["paper_official_execution_enabled"] is True
    assert row["paper_execution_policy"]["support"] == "paper_official_candidate"
    assert row["paper_execution_policy"]["live_enabled"] is False


def test_strategy_router_uses_no_trade_when_all_engines_weak():
    snapshot = _router().build_snapshot(
        instances=[{"symbol": "NEWEUR"}],
        paper_mode=True,
        setup_shadow_by_symbol={
            "NEWEUR": _symbol_payload("dynamic_grid", "grid_bad", 25.0, "weak", -2.0, 8)
        },
        trend_shadow_by_symbol={
            "NEWEUR": _symbol_payload("trend_momentum", "trend_bad", 30.0, "weak", -1.0, 8)
        },
        mean_reversion_shadow_by_symbol={
            "NEWEUR": _symbol_payload("mean_reversion", "mr_bad", 35.0, "weak", -0.5, 8)
        },
        opportunities=[],
    )

    row = snapshot["by_symbol"]["NEWEUR"]
    assert row["selected_engine"] == "no_trade"
    assert row["recommended_action"] == "no_trade"
    assert row["reason"] == "all_engines_weak"


def test_strategy_router_caps_learning_engine_before_evidence():
    snapshot = _router().build_snapshot(
        instances=[{"symbol": "NEWEUR"}],
        paper_mode=True,
        trend_shadow_by_symbol={
            "NEWEUR": _symbol_payload("trend_momentum", "trend_early", 95.0, "learning", 0.2, 0)
        },
        opportunities=[],
    )

    row = snapshot["by_symbol"]["NEWEUR"]
    assert row["selected_engine"] in {"trend_momentum", "no_trade"}
    trend = next(engine for engine in row["engines"] if engine["engine"] == "trend_momentum")
    assert trend["router_score"] <= 62.0
    assert row["recommended_action"] in {"continue_shadow_learning", "no_trade"}
