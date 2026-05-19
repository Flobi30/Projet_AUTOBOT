from autobot.v2.setup_optimizer import PairSetupOptimizer, SetupOptimizerConfig
from autobot.v2.setup_shadow_lab import SetupShadowLab, SetupShadowLabConfig

import pytest


pytestmark = pytest.mark.unit


def _lab(tmp_path) -> SetupShadowLab:
    return SetupShadowLab(
        SetupShadowLabConfig(
            db_path=str(tmp_path / "setup_shadow_lab.db"),
            virtual_capital_per_variant=100.0,
            min_tick_seconds=0,
            persist_interval_seconds=1,
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
            min_samples_for_signal=1,
            min_closed_trades_for_signal=1,
            candidate_score=50.0,
            candidate_profit_factor=1.0,
        )
    )


def test_setup_shadow_lab_runs_variants_without_official_paper_ledger(tmp_path):
    lab = _lab(tmp_path)

    lab.on_price_tick(symbol="NEWEUR", price=100.0, timestamp="2026-05-19T00:00:00+00:00")
    lab.on_price_tick(symbol="NEWEUR", price=102.0, timestamp="2026-05-19T00:01:00+00:00")
    lab.flush()

    snapshot = lab.build_snapshot(symbols=["NEWEUR"])
    assert snapshot["paper_only"] is True
    assert snapshot["writes_official_paper_ledger"] is False
    assert snapshot["summary"]["symbols"] == 1
    row = snapshot["by_symbol"]["NEWEUR"]
    assert row["best_variant"]["closed_trades"] >= 1
    assert row["best_variant"]["net_pnl_eur"] > 0

    reloaded = SetupShadowLab(lab.config)
    reloaded_snapshot = reloaded.build_snapshot(symbols=["NEWEUR"])
    assert reloaded_snapshot["by_symbol"]["NEWEUR"]["best_variant"]["closed_trades"] >= 1


def test_setup_optimizer_uses_shadow_variant_evidence_when_available():
    optimizer = PairSetupOptimizer(
        SetupOptimizerConfig(
            min_closed_trades=30,
            candidate_profit_factor=1.25,
            strong_profit_factor=1.60,
            candidate_score=70.0,
        )
    )

    snapshot = optimizer.build_snapshot(
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
        shadow_by_symbol={
            "NEWEUR": {
                "best_variant": {"variant": "grid_wide", "score": 88.0},
                "variants": [
                    {
                        "variant": "grid_wide",
                        "status": "candidate",
                        "score": 88.0,
                        "closed_trades": 12,
                        "net_pnl_eur": 2.4,
                        "profit_factor": 1.4,
                        "evidence_source": "setup_shadow_lab",
                    }
                ],
            }
        },
        paper_mode=True,
        total_capital=800.0,
    )

    row = snapshot["setups"][0]
    assert row["status"] == "candidate"
    assert row["recommended_action"] == "paper_shadow_candidate_review"
    assert row["selected_variant"]["name"] == "grid_wide"
    assert row["selected_variant"]["shadow_metrics"]["evidence_source"] == "setup_shadow_lab"
