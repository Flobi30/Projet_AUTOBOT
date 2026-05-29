import pytest

from autobot.v2.strategy_promotion_gate import StrategyPromotionGate, StrategyPromotionGateConfig
from autobot.v2.strategy_router import StrategyRouter, StrategyRouterConfig


pytestmark = pytest.mark.unit


def _router(promotion_gate_config: StrategyPromotionGateConfig | None = None) -> StrategyRouter:
    return StrategyRouter(
        StrategyRouterConfig(
            min_shadow_closed_trades=3,
            candidate_score=70.0,
            watch_score=55.0,
            weak_score=40.0,
            no_trade_score=50.0,
            evidence_cap_learning_score=62.0,
        ),
        promotion_gate_config
        or StrategyPromotionGateConfig(
            min_closed_trades=3,
            min_sample_count=20,
            min_profit_factor=1.2,
            min_net_pnl_eur=0.0,
            min_win_rate_pct=45.0,
            no_loss_min_closed_trades=10,
        ),
    )


def _symbol_payload(
    engine: str,
    variant: str,
    score: float,
    status: str,
    net: float,
    closed: int,
    validation_status: str = "shadow_passed",
):
    return {
        "symbol": "NEWEUR",
        "engine": engine,
        "best_variant": {
            "symbol": "NEWEUR",
            "engine": engine,
            "variant": variant,
            "status": status,
            "validation_status": validation_status,
            "score": score,
            "net_pnl_eur": net,
            "realized_pnl_eur": net,
            "profit_factor": 1.5 if net > 0 else 0.6,
            "win_rate": 60.0 if net > 0 else 35.0,
            "max_drawdown_eur": 0.5,
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
    assert row["promotion_gate"]["passed"] is True


def test_strategy_router_blocks_official_paper_when_promotion_gate_fails():
    snapshot = _router(
        StrategyPromotionGateConfig(
            min_closed_trades=30,
            min_sample_count=100,
            min_profit_factor=1.25,
            min_net_pnl_eur=0.0,
            min_win_rate_pct=45.0,
            no_loss_min_closed_trades=50,
        )
    ).build_snapshot(
        instances=[{"symbol": "NEWEUR"}],
        paper_mode=True,
        trend_shadow_by_symbol={
            "NEWEUR": _symbol_payload("trend_momentum", "trend_tiny_sample", 90.0, "candidate", 3.0, 5)
        },
        opportunities=[],
    )

    row = snapshot["by_symbol"]["NEWEUR"]
    assert row["selected_engine"] == "trend_momentum"
    assert row["recommended_action"] == "shadow_candidate_review"
    assert row["official_execution_enabled"] is False
    assert row["paper_official_execution_enabled"] is False
    assert row["paper_execution_policy"]["support"] == "shadow_only"
    assert row["promotion_gate"]["passed"] is False
    assert row["promotion_gate"]["status"] == "learning"
    assert "closed_trades" in row["promotion_gate"]["reason"]
    assert snapshot["summary"]["promotion_blocked_symbols"] == 1


def test_strategy_router_blocks_official_paper_without_research_workflow_stage():
    snapshot = _router().build_snapshot(
        instances=[{"symbol": "NEWEUR"}],
        paper_mode=True,
        trend_shadow_by_symbol={
            "NEWEUR": _symbol_payload(
                "trend_momentum",
                "trend_candidate_without_research_stage",
                90.0,
                "candidate",
                3.0,
                5,
                validation_status="candidate",
            )
        },
        opportunities=[],
    )

    row = snapshot["by_symbol"]["NEWEUR"]
    assert row["recommended_action"] == "shadow_candidate_review"
    assert row["official_execution_enabled"] is False
    assert row["promotion_gate"]["passed"] is False
    assert "research_validation_status" in row["promotion_gate"]["reason"]


def test_promotion_gate_blocks_learning_strategy_directly():
    gate = StrategyPromotionGate(
        StrategyPromotionGateConfig(
            min_closed_trades=3,
            min_sample_count=20,
            min_profit_factor=1.2,
            min_net_pnl_eur=0.0,
            min_win_rate_pct=45.0,
        )
    )
    result = gate.evaluate(
        {
            "engine": "dynamic_grid",
            "validation_status": "learning",
            "closed_trades": 10,
            "sample_count": 100,
            "net_pnl_eur": 3.0,
            "profit_factor": 1.5,
            "win_rate": 60.0,
        },
        "shadow_candidate_review",
        paper_mode=True,
    )

    assert result["passed"] is False
    assert "research_validation_status" in result["reason"]


def test_promotion_gate_blocks_unknown_strategy_engine_by_default():
    gate = StrategyPromotionGate(
        StrategyPromotionGateConfig(
            min_closed_trades=3,
            min_sample_count=20,
            min_profit_factor=1.2,
            min_net_pnl_eur=0.0,
            min_win_rate_pct=45.0,
        )
    )
    result = gate.evaluate(
        {
            "engine": "mystery_engine",
            "validation_status": "paper_validated",
            "closed_trades": 100,
            "sample_count": 500,
            "net_pnl_eur": 30.0,
            "profit_factor": 2.0,
            "win_rate": 70.0,
        },
        "shadow_candidate_review",
        paper_mode=True,
    )

    assert result["passed"] is False
    assert result["reason"] == "unknown_strategy_engine"


def test_promotion_gate_keeps_paper_validated_strategy_blocked_in_live_mode():
    gate = StrategyPromotionGate(
        StrategyPromotionGateConfig(
            min_closed_trades=3,
            min_sample_count=20,
            min_profit_factor=1.2,
            min_net_pnl_eur=0.0,
            min_win_rate_pct=45.0,
        )
    )
    result = gate.evaluate(
        {
            "engine": "dynamic_grid",
            "validation_status": "paper_validated",
            "closed_trades": 100,
            "sample_count": 500,
            "net_pnl_eur": 30.0,
            "profit_factor": 2.0,
            "win_rate": 70.0,
        },
        "shadow_candidate_review",
        paper_mode=False,
    )

    assert result["passed"] is False
    assert result["reason"] == "not_paper_mode"
    assert result["live_enabled"] is False


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
