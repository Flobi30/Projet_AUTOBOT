from autobot.v2.portfolio_allocator import AllocationConstraints, PortfolioAllocator


def _allocator():
    return PortfolioAllocator(
        AllocationConstraints(
            max_capital_per_instance_ratio=0.10,
            max_capital_per_cluster_ratio=0.30,
            reserve_cash_ratio=0.20,
            max_total_active_risk_ratio=0.20,
            risk_per_capital_ratio=0.02,
        )
    )


def test_portfolio_allocator_enforces_per_instance_cap():
    allocator = _allocator()
    plan = allocator.build_plan(
        ranked_candidates=["BTC/EUR"],
        total_capital=10_000,
        current_symbol_exposure={"BTC/EUR": 0.0},
        current_cluster_exposure={"BTC": 0.0},
        current_active_risk=0.0,
        symbol_to_cluster={"BTC/EUR": "BTC"},
    )

    assert plan.symbol_caps["BTC/EUR"] <= 1000.0


def test_portfolio_allocator_enforces_per_cluster_cap():
    allocator = _allocator()
    plan = allocator.build_plan(
        ranked_candidates=["BTC/EUR", "BTC/USD"],
        total_capital=10_000,
        current_symbol_exposure={"BTC/EUR": 0.0, "BTC/USD": 0.0},
        current_cluster_exposure={"BTC": 2500.0},
        current_active_risk=0.0,
        symbol_to_cluster={"BTC/EUR": "BTC", "BTC/USD": "BTC"},
    )

    # cluster cap = 3000, only ~500 left for BTC cluster across both symbols
    assert sum(plan.symbol_caps.values()) <= 500.0 + 1e-6


def test_portfolio_allocator_preserves_reserve_cash():
    allocator = _allocator()
    plan = allocator.build_plan(
        ranked_candidates=["BTC/EUR", "ETH/EUR", "SOL/EUR"],
        total_capital=10_000,
        current_symbol_exposure={},
        current_cluster_exposure={},
        current_active_risk=0.0,
        symbol_to_cluster={"BTC/EUR": "BTC", "ETH/EUR": "ETH", "SOL/EUR": "ALTS"},
    )

    assert plan.reserve_cash >= 2000.0
    assert plan.total_allocated <= 8000.0


def test_portfolio_allocator_enforces_max_total_active_risk_cap():
    allocator = _allocator()
    # active risk cap abs = 2000; current risk already 1990 => tiny room only
    plan = allocator.build_plan(
        ranked_candidates=["BTC/EUR", "ETH/EUR"],
        total_capital=10_000,
        current_symbol_exposure={"BTC/EUR": 0.0, "ETH/EUR": 0.0},
        current_cluster_exposure={"BTC": 0.0, "ETH": 0.0},
        current_active_risk=1990.0,
        symbol_to_cluster={"BTC/EUR": "BTC", "ETH/EUR": "ETH"},
    )

    assert plan.total_allocated <= 500.0 + 1e-6


def test_portfolio_allocator_explainability_payload():
    allocator = _allocator()
    plan = allocator.build_plan(
        ranked_candidates=["BTC/EUR"],
        total_capital=10_000,
        current_symbol_exposure={"BTC/EUR": 1000.0},
        current_cluster_exposure={"BTC": 3000.0},
        current_active_risk=2000.0,
        symbol_to_cluster={"BTC/EUR": "BTC"},
    )

    assert "max_instance_abs" in plan.explain
    assert "max_cluster_abs" in plan.explain
    assert "max_active_risk_abs" in plan.explain
    assert isinstance(plan.reasons, dict)
