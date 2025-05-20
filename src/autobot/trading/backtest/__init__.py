"""
Backtest module for AUTOBOT.

This module provides backtesting functionality for trading strategies.
"""

from autobot.trading.backtest.engine import run_backtest
from autobot.trading.backtest.backtester import Backtester
from autobot.trading.backtest.core import BacktestCore

__all__ = [
    'run_backtest',
    'Backtester',
    'BacktestCore'
]
