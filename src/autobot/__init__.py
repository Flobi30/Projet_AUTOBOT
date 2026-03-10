"""
AUTOBOT - Grid Trading Module pour Kraken
"""

__version__ = "1.0.0"
__author__ = "AUTOBOT Team"

from .grid_calculator import GridCalculator
from .order_manager import OrderManager
from .position_manager import PositionManager
from .error_handler import ErrorHandler

__all__ = ['GridCalculator', 'OrderManager', 'PositionManager', 'ErrorHandler']
