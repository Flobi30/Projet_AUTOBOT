"""
Visualization package for AUTOBOT.
Provides advanced data visualization tools for trading, portfolio analysis, and market data.
"""

from .chart_generator import (
    generate_candlestick_chart,
    generate_portfolio_chart,
    generate_correlation_matrix,
    generate_volume_profile,
    generate_market_depth,
    generate_performance_metrics
)

from .dashboard_components import (
    create_trading_dashboard,
    create_market_overview,
    create_portfolio_summary,
    create_strategy_performance
)

__all__ = [
    'generate_candlestick_chart',
    'generate_portfolio_chart',
    'generate_correlation_matrix',
    'generate_volume_profile',
    'generate_market_depth',
    'generate_performance_metrics',
    'create_trading_dashboard',
    'create_market_overview',
    'create_portfolio_summary',
    'create_strategy_performance'
]
