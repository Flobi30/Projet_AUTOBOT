"""
Grid Calculator Module for AUTOBOT Grid Trading Engine.

Calculates 15 equidistant grid levels within a +/-7% range around
the central price. Each level represents a buy/sell zone with
allocated capital for grid trading strategy.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class GridSide(Enum):
    """Side of the grid relative to center price."""
    BUY = "buy"
    SELL = "sell"
    CENTER = "center"


@dataclass
class GridConfig:
    """
    Configuration for grid trading strategy.
    
    Attributes:
        symbol: Trading pair (e.g., 'BTC/USDT')
        total_capital: Total capital allocated to grid (in quote currency)
        num_levels: Number of grid levels (default: 15)
        range_percent: Total range as percentage (default: 14% = +/-7%)
        profit_per_level: Target profit per level (default: 0.8%)
        min_order_size: Minimum order size for the exchange
        fee_percent: Trading fee percentage (default: 0.1% for Binance)
    """
    symbol: str
    total_capital: float
    num_levels: int = 15
    range_percent: float = 14.0  # +/-7% = 14% total range
    profit_per_level: float = 0.8
    min_order_size: float = 0.0001  # BTC minimum
    fee_percent: float = 0.1
    
    @property
    def capital_per_level(self) -> float:
        """Calculate capital allocated per grid level."""
        return self.total_capital / self.num_levels
    
    @property
    def half_range_percent(self) -> float:
        """Get half of the range (for +/- calculation)."""
        return self.range_percent / 2.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "symbol": self.symbol,
            "total_capital": self.total_capital,
            "num_levels": self.num_levels,
            "range_percent": self.range_percent,
            "profit_per_level": self.profit_per_level,
            "capital_per_level": self.capital_per_level,
            "min_order_size": self.min_order_size,
            "fee_percent": self.fee_percent,
        }


@dataclass
class GridLevel:
    """
    Represents a single grid level with price and order information.
    
    Attributes:
        level_id: Unique identifier for this level (0 = lowest)
        price: Price at this grid level
        side: Whether this is a buy or sell level
        allocated_capital: Capital allocated to this level
        quantity: Quantity to trade at this level
        is_active: Whether this level has an active order
        order_id: Exchange order ID if active
        filled_quantity: Amount filled at this level
        last_fill_time: Timestamp of last fill
    """
    level_id: int
    price: float
    side: GridSide
    allocated_capital: float
    quantity: float
    is_active: bool = False
    order_id: Optional[str] = None
    filled_quantity: float = 0.0
    last_fill_time: Optional[datetime] = None
    
    @property
    def is_filled(self) -> bool:
        """Check if level order is completely filled."""
        return self.filled_quantity >= self.quantity * 0.99  # 99% tolerance
    
    @property
    def fill_percent(self) -> float:
        """Get fill percentage."""
        if self.quantity == 0:
            return 0.0
        return (self.filled_quantity / self.quantity) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert level to dictionary."""
        return {
            "level_id": self.level_id,
            "price": self.price,
            "side": self.side.value,
            "allocated_capital": self.allocated_capital,
            "quantity": self.quantity,
            "is_active": self.is_active,
            "order_id": self.order_id,
            "filled_quantity": self.filled_quantity,
            "fill_percent": self.fill_percent,
            "last_fill_time": self.last_fill_time.isoformat() if self.last_fill_time else None,
        }


class GridCalculator:
    """
    Calculates and manages grid levels for grid trading strategy.
    
    The grid is calculated as follows:
    1. Determine upper and lower bounds (+/-7% from center)
    2. Create 15 equidistant levels within the range
    3. Levels below center are BUY levels
    4. Levels above center are SELL levels
    5. Allocate capital equally across all levels
    
    Example:
        config = GridConfig(symbol="BTC/USDT", total_capital=500.0)
        calculator = GridCalculator(config)
        levels = calculator.calculate_grid(center_price=50000.0)
    """
    
    def __init__(self, config: GridConfig):
        """
        Initialize grid calculator.
        
        Args:
            config: Grid configuration parameters
        """
        self.config = config
        self._levels: List[GridLevel] = []
        self._center_price: Optional[float] = None
        self._upper_bound: Optional[float] = None
        self._lower_bound: Optional[float] = None
        self._created_at: Optional[datetime] = None
        
        logger.info(
            f"GridCalculator initialized for {config.symbol} "
            f"with {config.num_levels} levels and {config.total_capital}€ capital"
        )
    
    @property
    def levels(self) -> List[GridLevel]:
        """Get all grid levels."""
        return self._levels
    
    @property
    def buy_levels(self) -> List[GridLevel]:
        """Get only buy levels (below center)."""
        return [l for l in self._levels if l.side == GridSide.BUY]
    
    @property
    def sell_levels(self) -> List[GridLevel]:
        """Get only sell levels (above center)."""
        return [l for l in self._levels if l.side == GridSide.SELL]
    
    @property
    def center_price(self) -> Optional[float]:
        """Get the center price of the grid."""
        return self._center_price
    
    @property
    def upper_bound(self) -> Optional[float]:
        """Get upper bound of the grid."""
        return self._upper_bound
    
    @property
    def lower_bound(self) -> Optional[float]:
        """Get lower bound of the grid."""
        return self._lower_bound
    
    @property
    def grid_spacing(self) -> Optional[float]:
        """Get the price spacing between levels."""
        if self._upper_bound is None or self._lower_bound is None:
            return None
        return (self._upper_bound - self._lower_bound) / (self.config.num_levels - 1)
    
    def calculate_grid(self, center_price: float) -> List[GridLevel]:
        """
        Calculate all grid levels based on center price.
        
        Args:
            center_price: The current/center price to build grid around
            
        Returns:
            List of GridLevel objects representing the grid
        """
        if center_price <= 0:
            raise ValueError("Center price must be positive")
        
        self._center_price = center_price
        self._created_at = datetime.utcnow()
        
        # Calculate bounds (+/-7% = 14% total range)
        half_range = self.config.half_range_percent / 100.0
        self._upper_bound = center_price * (1 + half_range)
        self._lower_bound = center_price * (1 - half_range)
        
        # Calculate price spacing between levels
        price_range = self._upper_bound - self._lower_bound
        spacing = price_range / (self.config.num_levels - 1)
        
        # Capital per level
        capital_per_level = self.config.capital_per_level
        
        # Create levels from lowest to highest
        self._levels = []
        center_level_idx = self.config.num_levels // 2
        
        for i in range(self.config.num_levels):
            price = self._lower_bound + (i * spacing)
            
            # Determine side based on position relative to center
            if i < center_level_idx:
                side = GridSide.BUY
            elif i > center_level_idx:
                side = GridSide.SELL
            else:
                side = GridSide.CENTER
            
            # Calculate quantity based on price and allocated capital
            quantity = capital_per_level / price
            
            # Ensure minimum order size
            if quantity < self.config.min_order_size:
                quantity = self.config.min_order_size
            
            level = GridLevel(
                level_id=i,
                price=round(price, 2),  # Round to 2 decimals for USDT
                side=side,
                allocated_capital=capital_per_level,
                quantity=round(quantity, 8),  # 8 decimals for BTC
            )
            
            self._levels.append(level)
        
        logger.info(
            f"Grid calculated: center={center_price:.2f}, "
            f"range=[{self._lower_bound:.2f}, {self._upper_bound:.2f}], "
            f"spacing={spacing:.2f}, levels={len(self._levels)}"
        )
        
        return self._levels
    
    def get_level_at_price(self, price: float) -> Optional[GridLevel]:
        """
        Find the grid level closest to a given price.
        
        Args:
            price: The price to find level for
            
        Returns:
            The closest GridLevel or None if outside grid
        """
        if not self._levels:
            return None
        
        if price < self._lower_bound or price > self._upper_bound:
            return None
        
        # Find closest level
        closest = min(self._levels, key=lambda l: abs(l.price - price))
        return closest
    
    def get_adjacent_levels(self, price: float) -> tuple:
        """
        Get the buy level below and sell level above a given price.
        
        Args:
            price: Current market price
            
        Returns:
            Tuple of (buy_level_below, sell_level_above) or (None, None)
        """
        if not self._levels:
            return (None, None)
        
        buy_level = None
        sell_level = None
        
        for level in self._levels:
            if level.price < price and level.side == GridSide.BUY:
                if buy_level is None or level.price > buy_level.price:
                    buy_level = level
            elif level.price > price and level.side == GridSide.SELL:
                if sell_level is None or level.price < sell_level.price:
                    sell_level = level
        
        return (buy_level, sell_level)
    
    def is_price_in_grid(self, price: float) -> bool:
        """
        Check if a price is within the grid range.
        
        Args:
            price: Price to check
            
        Returns:
            True if price is within grid bounds
        """
        if self._lower_bound is None or self._upper_bound is None:
            return False
        return self._lower_bound <= price <= self._upper_bound
    
    def get_distance_from_bounds(self, price: float) -> Dict[str, float]:
        """
        Calculate distance from grid bounds as percentage.
        
        Args:
            price: Current price
            
        Returns:
            Dict with distance_from_upper and distance_from_lower as percentages
        """
        if self._lower_bound is None or self._upper_bound is None:
            return {"distance_from_upper": 0.0, "distance_from_lower": 0.0}
        
        distance_from_upper = ((self._upper_bound - price) / price) * 100
        distance_from_lower = ((price - self._lower_bound) / price) * 100
        
        return {
            "distance_from_upper": round(distance_from_upper, 2),
            "distance_from_lower": round(distance_from_lower, 2),
        }
    
    def recalculate_grid(self, new_center_price: float) -> List[GridLevel]:
        """
        Recalculate grid with a new center price.
        
        This is used when the price moves outside the grid and
        rebalancing is needed.
        
        Args:
            new_center_price: New center price for the grid
            
        Returns:
            New list of GridLevel objects
        """
        logger.info(
            f"Recalculating grid: old_center={self._center_price}, "
            f"new_center={new_center_price}"
        )
        return self.calculate_grid(new_center_price)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current grid status.
        
        Returns:
            Dictionary with grid status information
        """
        active_levels = [l for l in self._levels if l.is_active]
        filled_levels = [l for l in self._levels if l.is_filled]
        
        return {
            "symbol": self.config.symbol,
            "center_price": self._center_price,
            "upper_bound": self._upper_bound,
            "lower_bound": self._lower_bound,
            "grid_spacing": self.grid_spacing,
            "total_levels": len(self._levels),
            "active_levels": len(active_levels),
            "filled_levels": len(filled_levels),
            "buy_levels": len(self.buy_levels),
            "sell_levels": len(self.sell_levels),
            "total_capital": self.config.total_capital,
            "capital_per_level": self.config.capital_per_level,
            "created_at": self._created_at.isoformat() if self._created_at else None,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert entire grid to dictionary for serialization.
        
        Returns:
            Dictionary representation of the grid
        """
        return {
            "config": self.config.to_dict(),
            "status": self.get_status(),
            "levels": [level.to_dict() for level in self._levels],
        }
