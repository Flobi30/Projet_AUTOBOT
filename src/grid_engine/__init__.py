"""
Grid Trading Engine for AUTOBOT Trading System.

This module provides a complete grid trading implementation with:
- Static grid calculation (15 levels, +/-7% range)
- Order management with automatic reinvestment
- Real-time P&L tracking
- Automatic rebalancing when price exits grid
- Risk management (stop loss, daily limits, emergency stop)

Target: BTC/USDT on Binance Spot
Capital: 500€ with ~33€ per level
Profit target: 0.8% per level, +15% monthly
"""

from .grid_calculator import GridCalculator, GridLevel, GridConfig
from .order_manager import GridOrderManager, GridOrder
from .position_tracker import PositionTracker, GridPosition, TradeRecord
from .rebalance import GridRebalancer, RebalanceAction
from .risk_manager import GridRiskManager, RiskStatus, RiskAlert
from .binance_connector import BinanceConnector, BinanceConfig
from .paper_trading_logger import PaperTradingLogger, DailyMetrics, CumulativeMetrics
from .position_manager import GridPositionManager, ManagedPosition, PositionStatus
from .api import router as grid_router

__all__ = [
    # Grid Calculator
    "GridCalculator",
    "GridLevel",
    "GridConfig",
    # Order Manager
    "GridOrderManager",
    "GridOrder",
    # Position Tracker
    "PositionTracker",
    "GridPosition",
    "TradeRecord",
    # Rebalancer
    "GridRebalancer",
    "RebalanceAction",
    # Risk Manager
    "GridRiskManager",
    "RiskStatus",
    "RiskAlert",
    # Binance Connector
    "BinanceConnector",
    "BinanceConfig",
    # Paper Trading Logger
    "PaperTradingLogger",
    "DailyMetrics",
    "CumulativeMetrics",
    # Position Manager
    "GridPositionManager",
    "ManagedPosition",
    "PositionStatus",
    # API Router
    "grid_router",
]

__version__ = "1.0.0"
