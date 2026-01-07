"""
AUTOBOT Macro-Economic Module

This module provides macro-economic analysis capabilities for trading decisions:
- Automatic retrieval of global macro indicators (CPI, PPI, NFP, interest rates, etc.)
- Economic regime detection (risk-on/risk-off, tightening/easing)
- Strategy adjustment based on macro context
- Exposure reduction during dangerous macro periods
- Signal reinforcement when macro validates trends
"""

from autobot.macro.indicators import MacroIndicatorManager
from autobot.macro.regime import RegimeDetector, MarketRegime
from autobot.macro.strategy_adjuster import MacroStrategyAdjuster

__all__ = [
    "MacroIndicatorManager",
    "RegimeDetector",
    "MarketRegime",
    "MacroStrategyAdjuster",
]
