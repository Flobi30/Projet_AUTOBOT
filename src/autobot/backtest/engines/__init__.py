"""
AUTOBOT Backtest Engines

This module provides adapters for various backtest engines:
- SimpleEngine: Built-in vectorized backtest (always available)
- BacktraderEngine: Adapter for Backtrader library
- VectorbtEngine: Adapter for vectorbt library
- FreqtradeEngine: Adapter for Freqtrade (future)
"""

from autobot.backtest.engines.base import BaseEngine, EngineCapabilities
from autobot.backtest.engines.simple import SimpleEngine

# Try to import optional engines
try:
    from autobot.backtest.engines.backtrader_adapter import BacktraderEngine
    BACKTRADER_AVAILABLE = True
except ImportError:
    BacktraderEngine = None
    BACKTRADER_AVAILABLE = False

try:
    from autobot.backtest.engines.vectorbt_adapter import VectorbtEngine
    VECTORBT_AVAILABLE = True
except ImportError:
    VectorbtEngine = None
    VECTORBT_AVAILABLE = False

__all__ = [
    "BaseEngine",
    "EngineCapabilities",
    "SimpleEngine",
    "BacktraderEngine",
    "VectorbtEngine",
    "BACKTRADER_AVAILABLE",
    "VECTORBT_AVAILABLE",
]
