"""
Simulation module for AUTOBOT.
Provides tools for simulating market conditions and backtesting trading strategies.
"""

from .market_simulator import (
    MarketSimulator,
    MarketCondition,
    MarketEvent
)

__all__ = [
    'MarketSimulator',
    'MarketCondition',
    'MarketEvent'
]
