"""
Rebalance Module for AUTOBOT Grid Trading Engine.

Handles automatic grid rebalancing when price moves outside
the grid range. Recalculates grid levels and manages the
transition to the new grid configuration.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable

from .grid_calculator import GridCalculator, GridConfig, GridLevel, GridSide
from .order_manager import GridOrderManager
from .position_tracker import PositionTracker, TradeType

logger = logging.getLogger(__name__)


class RebalanceReason(Enum):
    """Reason for grid rebalance."""
    PRICE_ABOVE_GRID = "price_above_grid"
    PRICE_BELOW_GRID = "price_below_grid"
    MANUAL_REBALANCE = "manual_rebalance"
    SCHEDULED_REBALANCE = "scheduled_rebalance"
    VOLATILITY_ADJUSTMENT = "volatility_adjustment"


class RebalanceStatus(Enum):
    """Status of rebalance operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class RebalanceAction:
    """
    Represents a rebalance action with details.
    
    Attributes:
        action_id: Unique identifier
        reason: Reason for rebalance
        old_center_price: Previous center price
        new_center_price: New center price
        old_bounds: Previous grid bounds
        new_bounds: New grid bounds
        orders_canceled: Number of orders canceled
        orders_placed: Number of new orders placed
        positions_closed: Number of positions closed
        status: Current status
        timestamp: Action timestamp
        error: Error message if failed
    """
    action_id: str
    reason: RebalanceReason
    old_center_price: float
    new_center_price: float
    old_bounds: tuple
    new_bounds: tuple
    orders_canceled: int = 0
    orders_placed: int = 0
    positions_closed: int = 0
    realized_pnl: float = 0.0
    status: RebalanceStatus = RebalanceStatus.PENDING
    timestamp: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action_id": self.action_id,
            "reason": self.reason.value,
            "old_center_price": self.old_center_price,
            "new_center_price": self.new_center_price,
            "old_bounds": self.old_bounds,
            "new_bounds": self.new_bounds,
            "orders_canceled": self.orders_canceled,
            "orders_placed": self.orders_placed,
            "positions_closed": self.positions_closed,
            "realized_pnl": round(self.realized_pnl, 2),
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class GridRebalancer:
    """
    Manages grid rebalancing when price exits the grid range.
    
    The rebalancer monitors price relative to grid bounds and
    triggers rebalancing when necessary. During rebalance:
    1. Cancel all active orders
    2. Close positions if configured
    3. Recalculate grid with new center price
    4. Place new orders
    
    Example:
        rebalancer = GridRebalancer(
            grid_calculator=calculator,
            order_manager=order_manager,
            position_tracker=tracker
        )
        
        # Check if rebalance needed
        if rebalancer.should_rebalance(current_price):
            action = await rebalancer.execute_rebalance(current_price)
    """
    
    def __init__(
        self,
        grid_calculator: GridCalculator,
        order_manager: GridOrderManager,
        position_tracker: PositionTracker,
        rebalance_threshold_percent: float = 1.0,
        close_positions_on_rebalance: bool = False,
        min_rebalance_interval_seconds: int = 300
    ):
        """
        Initialize rebalancer.
        
        Args:
            grid_calculator: GridCalculator instance
            order_manager: GridOrderManager instance
            position_tracker: PositionTracker instance
            rebalance_threshold_percent: Extra threshold before triggering rebalance
            close_positions_on_rebalance: Whether to close positions during rebalance
            min_rebalance_interval_seconds: Minimum time between rebalances
        """
        self.grid_calculator = grid_calculator
        self.order_manager = order_manager
        self.position_tracker = position_tracker
        self.rebalance_threshold = rebalance_threshold_percent
        self.close_positions = close_positions_on_rebalance
        self.min_interval = min_rebalance_interval_seconds
        
        self._rebalance_history: List[RebalanceAction] = []
        self._last_rebalance_time: Optional[datetime] = None
        self._rebalance_count: int = 0
        self._is_rebalancing: bool = False
        
        self._on_rebalance_start_callbacks: List[Callable] = []
        self._on_rebalance_complete_callbacks: List[Callable] = []
        
        logger.info(
            f"GridRebalancer initialized with threshold={rebalance_threshold_percent}%, "
            f"close_positions={close_positions_on_rebalance}"
        )
    
    @property
    def rebalance_history(self) -> List[RebalanceAction]:
        """Get rebalance history."""
        return self._rebalance_history
    
    @property
    def rebalance_count(self) -> int:
        """Get total rebalance count."""
        return self._rebalance_count
    
    @property
    def is_rebalancing(self) -> bool:
        """Check if rebalance is in progress."""
        return self._is_rebalancing
    
    @property
    def last_rebalance_time(self) -> Optional[datetime]:
        """Get time of last rebalance."""
        return self._last_rebalance_time
    
    def on_rebalance_start(self, callback: Callable) -> None:
        """Register callback for rebalance start."""
        self._on_rebalance_start_callbacks.append(callback)
    
    def on_rebalance_complete(self, callback: Callable) -> None:
        """Register callback for rebalance completion."""
        self._on_rebalance_complete_callbacks.append(callback)
    
    def should_rebalance(self, current_price: float) -> tuple:
        """
        Check if grid should be rebalanced.
        
        Args:
            current_price: Current market price
            
        Returns:
            Tuple of (should_rebalance: bool, reason: RebalanceReason or None)
        """
        if self._is_rebalancing:
            return (False, None)
        
        if self._last_rebalance_time:
            elapsed = (datetime.utcnow() - self._last_rebalance_time).total_seconds()
            if elapsed < self.min_interval:
                return (False, None)
        
        upper_bound = self.grid_calculator.upper_bound
        lower_bound = self.grid_calculator.lower_bound
        
        if upper_bound is None or lower_bound is None:
            return (False, None)
        
        threshold_multiplier = 1 + (self.rebalance_threshold / 100)
        
        if current_price > upper_bound * threshold_multiplier:
            return (True, RebalanceReason.PRICE_ABOVE_GRID)
        
        if current_price < lower_bound / threshold_multiplier:
            return (True, RebalanceReason.PRICE_BELOW_GRID)
        
        return (False, None)
    
    def get_distance_from_bounds(self, current_price: float) -> Dict[str, float]:
        """
        Get distance from grid bounds.
        
        Args:
            current_price: Current market price
            
        Returns:
            Dictionary with distance percentages
        """
        return self.grid_calculator.get_distance_from_bounds(current_price)
    
    async def execute_rebalance(
        self,
        new_center_price: float,
        reason: RebalanceReason = RebalanceReason.MANUAL_REBALANCE
    ) -> RebalanceAction:
        """
        Execute grid rebalance.
        
        Args:
            new_center_price: New center price for the grid
            reason: Reason for rebalance
            
        Returns:
            RebalanceAction with results
        """
        import uuid
        
        if self._is_rebalancing:
            raise RuntimeError("Rebalance already in progress")
        
        self._is_rebalancing = True
        
        action = RebalanceAction(
            action_id=str(uuid.uuid4()),
            reason=reason,
            old_center_price=self.grid_calculator.center_price or 0,
            new_center_price=new_center_price,
            old_bounds=(
                self.grid_calculator.lower_bound or 0,
                self.grid_calculator.upper_bound or 0
            ),
            new_bounds=(0, 0),  # Will be updated
            status=RebalanceStatus.IN_PROGRESS,
        )
        
        for callback in self._on_rebalance_start_callbacks:
            try:
                await callback(action)
            except Exception as e:
                logger.error(f"Rebalance start callback error: {e}")
        
        try:
            logger.info(
                f"Starting rebalance: {reason.value}, "
                f"old_center={action.old_center_price}, new_center={new_center_price}"
            )
            
            canceled_count = await self.order_manager.cancel_all_orders()
            action.orders_canceled = canceled_count
            
            if self.close_positions:
                closed_count, realized_pnl = await self._close_all_positions(new_center_price)
                action.positions_closed = closed_count
                action.realized_pnl = realized_pnl
            
            new_levels = self.grid_calculator.recalculate_grid(new_center_price)
            
            action.new_bounds = (
                self.grid_calculator.lower_bound,
                self.grid_calculator.upper_bound
            )
            
            new_orders = await self.order_manager.initialize_grid_orders()
            action.orders_placed = len(new_orders)
            
            action.status = RebalanceStatus.COMPLETED
            action.completed_at = datetime.utcnow()
            
            self._rebalance_history.append(action)
            self._rebalance_count += 1
            self._last_rebalance_time = datetime.utcnow()
            
            logger.info(
                f"Rebalance completed: canceled={canceled_count}, "
                f"placed={len(new_orders)}, new_bounds={action.new_bounds}"
            )
            
        except Exception as e:
            action.status = RebalanceStatus.FAILED
            action.error = str(e)
            self._rebalance_history.append(action)
            logger.error(f"Rebalance failed: {e}")
            raise
            
        finally:
            self._is_rebalancing = False
            
            for callback in self._on_rebalance_complete_callbacks:
                try:
                    await callback(action)
                except Exception as e:
                    logger.error(f"Rebalance complete callback error: {e}")
        
        return action
    
    async def _close_all_positions(self, current_price: float) -> tuple:
        """
        Close all open positions at current price.
        
        Args:
            current_price: Price to close positions at
            
        Returns:
            Tuple of (positions_closed, realized_pnl)
        """
        closed_count = 0
        total_pnl = 0.0
        
        for position in list(self.position_tracker.open_positions):
            trade = self.position_tracker.record_trade(
                trade_type=TradeType.REBALANCE,
                side=GridSide.SELL,
                quantity=position.quantity,
                price=current_price,
                fee=position.quantity * current_price * (self.grid_calculator.config.fee_percent / 100),
                level_id=position.level_id,
            )
            
            total_pnl += trade.profit
            closed_count += 1
        
        return (closed_count, total_pnl)
    
    async def check_and_rebalance(self, current_price: float) -> Optional[RebalanceAction]:
        """
        Check if rebalance is needed and execute if so.
        
        Args:
            current_price: Current market price
            
        Returns:
            RebalanceAction if rebalance was executed, None otherwise
        """
        should_rebal, reason = self.should_rebalance(current_price)
        
        if not should_rebal:
            return None
        
        logger.info(f"Rebalance triggered: {reason.value} at price {current_price}")
        
        return await self.execute_rebalance(current_price, reason)
    
    def get_rebalance_recommendation(self, current_price: float) -> Dict[str, Any]:
        """
        Get recommendation for rebalance without executing.
        
        Args:
            current_price: Current market price
            
        Returns:
            Dictionary with recommendation details
        """
        should_rebal, reason = self.should_rebalance(current_price)
        distances = self.get_distance_from_bounds(current_price)
        
        config = self.grid_calculator.config
        half_range = config.half_range_percent
        
        new_upper = current_price * (1 + half_range / 100)
        new_lower = current_price * (1 - half_range / 100)
        
        return {
            "should_rebalance": should_rebal,
            "reason": reason.value if reason else None,
            "current_price": current_price,
            "current_bounds": {
                "lower": self.grid_calculator.lower_bound,
                "upper": self.grid_calculator.upper_bound,
            },
            "distance_from_bounds": distances,
            "recommended_new_bounds": {
                "lower": round(new_lower, 2),
                "upper": round(new_upper, 2),
            },
            "active_orders": len(self.order_manager.active_orders),
            "open_positions": len(self.position_tracker.open_positions),
            "time_since_last_rebalance": self._get_time_since_last_rebalance(),
            "min_interval_seconds": self.min_interval,
        }
    
    def _get_time_since_last_rebalance(self) -> Optional[float]:
        """Get seconds since last rebalance."""
        if self._last_rebalance_time is None:
            return None
        return (datetime.utcnow() - self._last_rebalance_time).total_seconds()
    
    def get_status(self) -> Dict[str, Any]:
        """Get rebalancer status."""
        return {
            "is_rebalancing": self._is_rebalancing,
            "rebalance_count": self._rebalance_count,
            "last_rebalance_time": self._last_rebalance_time.isoformat() if self._last_rebalance_time else None,
            "time_since_last_rebalance": self._get_time_since_last_rebalance(),
            "min_interval_seconds": self.min_interval,
            "rebalance_threshold_percent": self.rebalance_threshold,
            "close_positions_on_rebalance": self.close_positions,
            "current_bounds": {
                "lower": self.grid_calculator.lower_bound,
                "upper": self.grid_calculator.upper_bound,
            },
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert rebalancer state to dictionary."""
        return {
            "status": self.get_status(),
            "history": [a.to_dict() for a in self._rebalance_history[-20:]],
        }
