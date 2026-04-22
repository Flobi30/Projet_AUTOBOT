import pytest

from types import SimpleNamespace

from autobot.v2.orchestrator_services import InstanceLifecycleService, PortfolioAllocationService
from autobot.v2.portfolio_allocator import AllocationConstraints, PortfolioAllocator
from autobot.v2.risk_cluster_manager import RiskClusterManager


pytestmark = pytest.mark.integration

class _Inst:
    def __init__(self, symbol: str, cap: float, running: bool, pf30: float = 1.0):
        self.config = SimpleNamespace(symbol=symbol)
        self._cap = cap
        self._running = running
        self._pf30 = pf30

    def is_running(self):
        return self._running

    def get_current_capital(self):
        return self._cap

    def get_profit_factor_days(self, _days: int):
        return self._pf30


def test_portfolio_allocation_service_builds_plan():
    allocator = PortfolioAllocator(
        AllocationConstraints(
            max_capital_per_instance_ratio=0.5,
            max_capital_per_cluster_ratio=0.6,
            reserve_cash_ratio=0.1,
            max_total_active_risk_ratio=0.3,
            risk_per_capital_ratio=0.05,
        )
    )
    service = PortfolioAllocationService(allocator, RiskClusterManager(cluster_cap=0.5))
    instances = [_Inst("BTC/USD", 1000.0, True), _Inst("ETH/USD", 800.0, True)]

    plan = service.refresh_plan(
        instances=instances,
        fallback_instances=instances,
        ranked_symbols=["BTC/USD", "ETH/USD"],
    )

    assert plan is not None
    assert plan.total_allocated >= 0.0
    assert len(plan.symbol_caps) >= 1


def test_instance_lifecycle_service_selects_lowest_pf_first():
    service = InstanceLifecycleService()
    instances = [_Inst("BTC/USD", 1000.0, True, pf30=1.5), _Inst("ETH/USD", 1000.0, True, pf30=0.8)]
    victims = service.select_worst_by_pf(instances, 1)
    assert len(victims) == 1
    assert victims[0].config.symbol == "ETH/USD"
