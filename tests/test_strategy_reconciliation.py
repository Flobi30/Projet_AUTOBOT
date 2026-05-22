import pytest

from autobot.v2.strategy_reconciliation import StrategyReconciliationConfig, StrategyReconciliationEngine


pytestmark = pytest.mark.unit


def _engine() -> StrategyReconciliationEngine:
    return StrategyReconciliationEngine(
        StrategyReconciliationConfig(
            min_official_closed_trades=20,
            min_shadow_closed_trades=30,
            no_loss_shadow_min_closed_trades=50,
            min_positive_shadow_pnl_eur=0.0,
            fee_drag_warning_pct=35.0,
        )
    )


def test_reconciliation_flags_positive_shadow_against_negative_official_paper():
    snapshot = _engine().build_snapshot(
        official_performance={
            "source": "trade_ledger",
            "global": {
                "closed_trades": 40,
                "net_pnl": -2.5,
                "profit_factor": 0.7,
                "win_rate": 32.5,
            },
            "by_symbol": {
                "TRXEUR": {
                    "closed_trades": 40,
                    "net_pnl": -2.5,
                    "gross_profit": 1.0,
                    "gross_loss": 3.5,
                    "fees": 1.2,
                    "profit_factor": 0.7,
                    "win_rate": 32.5,
                }
            },
        },
        shadow_snapshots={
            "dynamic_grid": {
                "summary": {"closed_shadow_trades": 12, "net_shadow_pnl_eur": 4.2, "candidate_symbols": 1},
                "by_symbol": {
                    "TRXEUR": {
                        "best_variant": {
                            "variant": "grid_wide",
                            "status": "candidate",
                            "score": 92.0,
                            "closed_trades": 12,
                            "net_pnl_eur": 4.2,
                            "gross_profit_eur": 4.2,
                            "gross_loss_eur": 0.0,
                            "profit_factor": None,
                        }
                    }
                },
            }
        },
        paper_mode=True,
    )

    row = snapshot["symbols"][0]
    assert snapshot["paper_only"] is True
    assert snapshot["live_promotion_allowed"] is False
    assert row["symbol"] == "TRXEUR"
    assert row["verdict"] == "shadow_official_divergence"
    assert "shadow_positive_official_negative" in row["root_causes"]
    assert "shadow_has_no_losses_yet" in row["root_causes"]
    assert row["recommended_action"] == "do_not_promote_shadow_review_costs_and_execution"


def test_reconciliation_keeps_small_positive_shadow_in_learning_before_promotion():
    snapshot = _engine().build_snapshot(
        official_performance={
            "source": "trade_ledger",
            "global": {"closed_trades": 4, "net_pnl": 0.2, "profit_factor": 1.1, "win_rate": 50.0},
            "by_symbol": {
                "NEWEUR": {
                    "closed_trades": 4,
                    "net_pnl": 0.2,
                    "gross_profit": 0.5,
                    "gross_loss": 0.3,
                    "fees": 0.1,
                    "profit_factor": 1.1,
                    "win_rate": 50.0,
                }
            },
        },
        shadow_snapshots={
            "dynamic_grid": {
                "summary": {"closed_shadow_trades": 10, "net_shadow_pnl_eur": 1.0, "candidate_symbols": 1},
                "by_symbol": {
                    "NEWEUR": {
                        "best_variant": {
                            "variant": "grid_balanced",
                            "status": "candidate",
                            "score": 80.0,
                            "closed_trades": 10,
                            "net_pnl_eur": 1.0,
                            "gross_loss_eur": 0.2,
                            "profit_factor": 5.0,
                        }
                    }
                },
            }
        },
        paper_mode=True,
    )

    row = snapshot["symbols"][0]
    assert row["verdict"] == "shadow_sample_not_robust"
    assert row["recommended_action"] == "keep_shadow_learning_before_paper_promotion"
    assert "shadow_closed_trades_below_reconciliation_min" in row["root_causes"]


def test_reconciliation_accepts_only_aligned_positive_paper_and_shadow():
    snapshot = _engine().build_snapshot(
        official_performance={
            "source": "trade_ledger",
            "global": {"closed_trades": 45, "net_pnl": 3.0, "profit_factor": 1.4, "win_rate": 58.0},
            "by_symbol": {
                "TRXEUR": {
                    "closed_trades": 45,
                    "net_pnl": 3.0,
                    "gross_profit": 7.0,
                    "gross_loss": 4.0,
                    "fees": 1.0,
                    "profit_factor": 1.4,
                    "win_rate": 58.0,
                }
            },
        },
        shadow_snapshots={
            "dynamic_grid": {
                "summary": {"closed_shadow_trades": 55, "net_shadow_pnl_eur": 6.0, "candidate_symbols": 1},
                "by_symbol": {
                    "TRXEUR": {
                        "best_variant": {
                            "variant": "grid_wide",
                            "status": "candidate",
                            "score": 86.0,
                            "closed_trades": 55,
                            "net_pnl_eur": 6.0,
                            "gross_profit_eur": 8.0,
                            "gross_loss_eur": 2.0,
                            "profit_factor": 4.0,
                        }
                    }
                },
            }
        },
        paper_mode=True,
    )

    row = snapshot["symbols"][0]
    assert row["verdict"] == "aligned_positive"
    assert row["recommended_action"] == "continue_paper_observation_no_live_auto_promotion"
    assert snapshot["summary"]["requires_attention"] == 0
