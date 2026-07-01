from pathlib import Path

import pytest

from autobot.v2.research.research_paper_parity import ResearchPaperParityConfig
from autobot.v2.research.standard_audit_runner import StandardAuditConfig
from autobot.v2.strategy_promotion_gate import StrategyPromotionGate
from autobot.v2.strategy_validation_registry import (
    PROMOTABLE_STRATEGY_IDS,
    can_execute_official_paper,
    can_request_live_review,
    entry_by_strategy_id,
    load_registry,
)


pytestmark = pytest.mark.unit


REGISTRY_PATH = Path("docs/research/strategy_hypotheses.json")


def test_standard_research_defaults_exclude_archived_grid(tmp_path):
    standard = StandardAuditConfig(
        run_id="pytest_standard_defaults",
        state_db_path=tmp_path / "state.db",
        symbols=("TRXEUR",),
    )
    parity = ResearchPaperParityConfig(
        run_id="pytest_parity_defaults",
        state_db_path=tmp_path / "state.db",
        symbols=("TRXEUR",),
    )

    assert standard.strategies == ("trend", "mean_reversion")
    assert parity.strategies == ("trend", "mean_reversion")


def test_retired_grid_is_blocked_from_all_promotion_paths():
    registry = load_registry(REGISTRY_PATH)
    grid = dict(entry_by_strategy_id(registry, "dynamic_grid"))
    grid["validation_status"] = "paper_validated"

    result = StrategyPromotionGate().evaluate(
        {
            "engine": "dynamic_grid",
            "strategy_id": "dynamic_grid",
            "validation_status": "paper_validated",
            "closed_trades": 1_000,
            "sample_count": 1_000,
            "net_pnl_eur": 100.0,
            "profit_factor": 2.0,
            "win_rate": 75.0,
            "fees_included": True,
            "slippage_included": True,
            "baseline_comparison": {"baseline": "no_trade", "net_delta_eur": 100.0},
            "out_of_sample_periods": 1,
        },
        "shadow_candidate_review",
        paper_mode=True,
    )

    assert "dynamic_grid" not in PROMOTABLE_STRATEGY_IDS
    assert result["passed"] is False
    assert result["reason"] == "grid_retired_research_only"
    assert can_execute_official_paper(grid) is False
    assert can_request_live_review(grid) is False
