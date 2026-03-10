"""
AUTOBOT - Grid Trading Module pour Kraken
"""

__version__ = "1.1.0"
__author__ = "AUTOBOT Team"

from .grid_calculator import GridCalculator, GridConfig
from .order_manager import OrderManager, Order, OrderSide
from .position_manager import PositionManager, Position
from .error_handler import ErrorHandler
from .market_data import MarketData
from .state_manager import StateManager
from .rate_limiter import RateLimiter

__all__ = [
    'GridCalculator', 'GridConfig',
    'OrderManager', 'Order', 'OrderSide',
    'PositionManager', 'Position',
    'ErrorHandler',
    'MarketData',
    'StateManager',
    'RateLimiter'
]
