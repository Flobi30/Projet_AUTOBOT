from autobot.v2.portfolio_allocator import (
    AllocationConstraints,
    AllocationWeightProvider,
    PortfolioAllocator,
    SymbolMetrics,
    WeightConstraints,
)


pytestmark = pytest.mark.unit

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


def test_weight_provider_normalizes_weights_to_one():
    provider = AllocationWeightProvider(constraints=WeightConstraints(min_weight=0.05, max_weight=0.70))
    weights = provider.compute_weights(
        ["XXBTZEUR", "XETHZEUR", "ADAEUR"],
        metrics_by_symbol={
            "XXBTZEUR": SymbolMetrics(rolling_profit_factor=1.4, max_drawdown=0.15, realized_volatility=0.30, execution_cost=0.001, execution_stability=0.95),
            "XETHZEUR": SymbolMetrics(rolling_profit_factor=1.2, max_drawdown=0.20, realized_volatility=0.40, execution_cost=0.002, execution_stability=0.90),
            "ADAEUR": SymbolMetrics(rolling_profit_factor=0.9, max_drawdown=0.35, realized_volatility=0.70, execution_cost=0.004, execution_stability=0.70),
        },
    )

    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_weight_provider_respects_min_max_constraints():
    provider = AllocationWeightProvider(constraints=WeightConstraints(min_weight=0.10, max_weight=0.50))
    weights = provider.compute_weights(
        ["XXBTZEUR", "XETHZEUR", "ADAEUR", "SOLEUR"],
        metrics_by_symbol={
            "XXBTZEUR": SymbolMetrics(rolling_profit_factor=2.0, max_drawdown=0.05, realized_volatility=0.20, execution_cost=0.0008, execution_stability=0.98),
            "XETHZEUR": SymbolMetrics(rolling_profit_factor=0.8, max_drawdown=0.35, realized_volatility=0.80, execution_cost=0.006, execution_stability=0.60),
            "ADAEUR": SymbolMetrics(rolling_profit_factor=0.8, max_drawdown=0.35, realized_volatility=0.80, execution_cost=0.006, execution_stability=0.60),
            "SOLEUR": SymbolMetrics(rolling_profit_factor=0.8, max_drawdown=0.35, realized_volatility=0.80, execution_cost=0.006, execution_stability=0.60),
        },
    )

    assert all(0.10 - 1e-9 <= w <= 0.50 + 1e-9 for w in weights.values())


def test_weight_provider_conservative_fallback_for_missing_data():
    provider = AllocationWeightProvider(constraints=WeightConstraints(min_weight=0.05, max_weight=0.70))
    weights = provider.compute_weights(
        ["XXBTZEUR", "NEWCOIN"],
        metrics_by_symbol={
            "XXBTZEUR": SymbolMetrics(rolling_profit_factor=1.5, max_drawdown=0.12, realized_volatility=0.25, execution_cost=0.001, execution_stability=0.95),
            "NEWCOIN": SymbolMetrics(rolling_profit_factor=None, max_drawdown=None, realized_volatility=None, execution_cost=None, execution_stability=None),
        },
    )

    assert weights["NEWCOIN"] <= 0.30 + 1e-9
    assert weights["XXBTZEUR"] > weights["NEWCOIN"]


def test_weight_provider_legacy_baseline_non_regression_ordering():
    provider = AllocationWeightProvider(constraints=WeightConstraints(min_weight=0.05, max_weight=0.70, reserve_cash_ratio=0.20))
    plan = provider.build_weighted_capital_plan(["XXBTZEUR", "XETHZEUR", "ADAEUR"], total_capital=1_000)

    assert plan.reserve_cash == 200.0
    assert plan.total_allocated == 800.0
    assert plan.symbol_caps["XXBTZEUR"] > plan.symbol_caps["XETHZEUR"] > plan.symbol_caps["ADAEUR"]
