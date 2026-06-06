import pytest

from autobot.v2.research.cost_parity_audit import CostParityAuditConfig, audit_cost_parity
from autobot.v2.research.execution_cost_model import ExecutionCostConfig


pytestmark = pytest.mark.unit


def test_research_cost_config_rejects_negative_costs():
    with pytest.raises(ValueError, match="cannot be negative"):
        ExecutionCostConfig(slippage_bps=-1.0).validate()


def test_cost_parity_audit_uses_conservative_research_baseline_when_paper_missing(tmp_path):
    missing_state_db = tmp_path / "missing_state.db"

    report = audit_cost_parity(
        CostParityAuditConfig(
            run_id="pytest_research_paper_cost_parity",
            state_db_path=missing_state_db,
            research_cost_config=ExecutionCostConfig(
                taker_fee_bps=16.0,
                maker_fee_bps=10.0,
                fallback_spread_bps=8.0,
                slippage_bps=4.0,
                latency_buffer_bps=1.0,
            ),
        )
    )

    assert report.expected_cost_bps_per_side > 0.0
    assert report.sources[0].source == "official_paper_trade_ledger"
    assert report.sources[0].status == "missing"
    assert "state_db_missing" in report.warnings
    assert "No live trading permission is granted." in report.safety_notes
