"""
Order Manager Module for AUTOBOT Grid Trading Engine.

Manages order placement, tracking, and automatic reinvestment
for grid trading strategy on Binance Spot.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
import uuid

from .grid_calculator import GridLevel, GridSide, GridCalculator

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Status of a grid order."""
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderType(Enum):
    """Type of order."""
    LIMIT = "limit"
    MARKET = "market"


@dataclass
class GridOrder:
    """
    Represents an order placed for a grid level.
    
    Attributes:
        order_id: Internal order ID
        exchange_order_id: Order ID from exchange
        level_id: Associated grid level ID
        symbol: Trading pair
        side: Buy or sell
        order_type: Limit or market
        price: Order price
        quantity: Order quantity
        filled_quantity: Amount filled
        status: Current order status
        created_at: Order creation time
        updated_at: Last update time
        fee: Trading fee paid
        fee_currency: Currency of fee
    """
    order_id: str
    level_id: int
    symbol: str
    side: GridSide
    order_type: OrderType
    price: float
    quantity: float
    exchange_order_id: Optional[str] = None
    filled_quantity: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    fee: float = 0.0
    fee_currency: str = "USDT"
    average_fill_price: Optional[float] = None
    
    @property
    def is_active(self) -> bool:
        """Check if order is still active."""
        return self.status in [OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]
    
    @property
    def is_complete(self) -> bool:
        """Check if order is complete (filled or canceled)."""
        return self.status in [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED]
    
    @property
    def remaining_quantity(self) -> float:
        """Get remaining quantity to fill."""
        return max(0, self.quantity - self.filled_quantity)
    
    @property
    def fill_percent(self) -> float:
        """Get fill percentage."""
        if self.quantity == 0:
            return 0.0
        return (self.filled_quantity / self.quantity) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert order to dictionary."""
        return {
            "order_id": self.order_id,
            "exchange_order_id": self.exchange_order_id,
            "level_id": self.level_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "price": self.price,
            "quantity": self.quantity,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "fill_percent": self.fill_percent,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "fee": self.fee,
            "fee_currency": self.fee_currency,
            "average_fill_price": self.average_fill_price,
        }


class GridOrderManager:
    """
    Manages orders for grid trading strategy.
    
    Responsibilities:
    - Place buy orders at buy levels
    - Place sell orders at sell levels
    - Track order status and fills
    - Reinvest profits by placing new orders
    - Handle order lifecycle (create, update, cancel)
    
    Example:
        calculator = GridCalculator(config)
        levels = calculator.calculate_grid(50000.0)
        
        manager = GridOrderManager(calculator)
        await manager.initialize_grid_orders()
        
        # When a buy order fills, place corresponding sell order
        await manager.on_order_filled(order_id)
    """
    
    def __init__(
        self,
        grid_calculator: GridCalculator,
        exchange_client: Optional[Any] = None,
        paper_trading: bool = True
    ):
        """
        Initialize order manager.
        
        Args:
            grid_calculator: GridCalculator instance with calculated levels
            exchange_client: Exchange client for placing orders (optional)
            paper_trading: If True, simulate orders without real execution
        """
        self.grid_calculator = grid_calculator
        self.exchange_client = exchange_client
        self.paper_trading = paper_trading
        
        self._orders: Dict[str, GridOrder] = {}
        self._level_orders: Dict[int, str] = {}  # level_id -> order_id
        self._filled_orders: List[GridOrder] = []
        self._total_profit: float = 0.0
        self._total_fees: float = 0.0
        self._trade_count: int = 0
        
        self._on_order_filled_callbacks: List[Callable] = []
        self._on_order_canceled_callbacks: List[Callable] = []
        
        logger.info(
            f"GridOrderManager initialized for {grid_calculator.config.symbol}, "
            f"paper_trading={paper_trading}"
        )
    
    @property
    def orders(self) -> Dict[str, GridOrder]:
        """Get all orders."""
        return self._orders
    
    @property
    def active_orders(self) -> List[GridOrder]:
        """Get all active orders."""
        return [o for o in self._orders.values() if o.is_active]
    
    @property
    def buy_orders(self) -> List[GridOrder]:
        """Get all buy orders."""
        return [o for o in self._orders.values() if o.side == GridSide.BUY]
    
    @property
    def sell_orders(self) -> List[GridOrder]:
        """Get all sell orders."""
        return [o for o in self._orders.values() if o.side == GridSide.SELL]
    
    @property
    def total_profit(self) -> float:
        """Get total profit from completed trades."""
        return self._total_profit
    
    @property
    def total_fees(self) -> float:
        """Get total fees paid."""
        return self._total_fees
    
    @property
    def trade_count(self) -> int:
        """Get total number of completed trades."""
        return self._trade_count
    
    def on_order_filled(self, callback: Callable) -> None:
        """Register callback for order filled events."""
        self._on_order_filled_callbacks.append(callback)
    
    def on_order_canceled(self, callback: Callable) -> None:
        """Register callback for order canceled events."""
        self._on_order_canceled_callbacks.append(callback)
    
    async def initialize_grid_orders(self) -> List[GridOrder]:
        """
        Initialize orders for all grid levels.
        
        Places buy orders at all buy levels and prepares
        sell orders (to be placed when buys fill).
        
        Returns:
            List of created orders
        """
        created_orders = []
        
        for level in self.grid_calculator.levels:
            if level.side == GridSide.BUY:
                order = await self.place_order_for_level(level)
                if order:
                    created_orders.append(order)
            elif level.side == GridSide.SELL:
                pass
        
        logger.info(f"Initialized {len(created_orders)} grid orders")
        return created_orders
    
    async def place_order_for_level(
        self,
        level: GridLevel,
        order_type: OrderType = OrderType.LIMIT
    ) -> Optional[GridOrder]:
        """
        Place an order for a specific grid level.
        
        Args:
            level: Grid level to place order for
            order_type: Type of order (limit or market)
            
        Returns:
            Created GridOrder or None if failed
        """
        if level.level_id in self._level_orders:
            existing_order_id = self._level_orders[level.level_id]
            existing_order = self._orders.get(existing_order_id)
            if existing_order and existing_order.is_active:
                logger.warning(f"Level {level.level_id} already has active order")
                return None
        
        order = GridOrder(
            order_id=str(uuid.uuid4()),
            level_id=level.level_id,
            symbol=self.grid_calculator.config.symbol,
            side=level.side,
            order_type=order_type,
            price=level.price,
            quantity=level.quantity,
        )
        
        if self.paper_trading:
            order.status = OrderStatus.OPEN
            order.exchange_order_id = f"PAPER_{order.order_id[:8]}"
        else:
            exchange_order = await self._place_exchange_order(order)
            if exchange_order:
                order.exchange_order_id = exchange_order.get("orderId")
                order.status = OrderStatus.OPEN
            else:
                order.status = OrderStatus.REJECTED
                logger.error(f"Failed to place order for level {level.level_id}")
                return None
        
        self._orders[order.order_id] = order
        self._level_orders[level.level_id] = order.order_id
        
        level.is_active = True
        level.order_id = order.order_id
        
        logger.info(
            f"Placed {order.side.value} order at {order.price} "
            f"for {order.quantity} {order.symbol}"
        )
        
        return order
    
    async def _place_exchange_order(self, order: GridOrder) -> Optional[Dict[str, Any]]:
        """
        Place order on exchange.
        
        Args:
            order: Order to place
            
        Returns:
            Exchange response or None if failed
        """
        if self.exchange_client is None:
            logger.warning("No exchange client configured")
            return None
        
        try:
            side = "BUY" if order.side == GridSide.BUY else "SELL"
            
            response = await self.exchange_client.create_order(
                symbol=order.symbol.replace("/", ""),
                side=side,
                type=order.order_type.value.upper(),
                quantity=order.quantity,
                price=order.price if order.order_type == OrderType.LIMIT else None,
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Exchange order failed: {e}")
            return None
    
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if canceled successfully
        """
        order = self._orders.get(order_id)
        if not order:
            logger.warning(f"Order {order_id} not found")
            return False
        
        if not order.is_active:
            logger.warning(f"Order {order_id} is not active")
            return False
        
        if self.paper_trading:
            order.status = OrderStatus.CANCELED
        else:
            try:
                await self.exchange_client.cancel_order(
                    symbol=order.symbol.replace("/", ""),
                    orderId=order.exchange_order_id,
                )
                order.status = OrderStatus.CANCELED
            except Exception as e:
                logger.error(f"Failed to cancel order: {e}")
                return False
        
        order.updated_at = datetime.utcnow()
        
        level = self._get_level_for_order(order)
        if level:
            level.is_active = False
            level.order_id = None
        
        for callback in self._on_order_canceled_callbacks:
            try:
                await callback(order)
            except Exception as e:
                logger.error(f"Order canceled callback error: {e}")
        
        logger.info(f"Canceled order {order_id}")
        return True
    
    async def cancel_all_orders(self) -> int:
        """
        Cancel all active orders.
        
        Returns:
            Number of orders canceled
        """
        canceled_count = 0
        
        for order in list(self.active_orders):
            if await self.cancel_order(order.order_id):
                canceled_count += 1
        
        logger.info(f"Canceled {canceled_count} orders")
        return canceled_count
    
    async def update_order_status(
        self,
        order_id: str,
        status: OrderStatus,
        filled_quantity: Optional[float] = None,
        average_fill_price: Optional[float] = None,
        fee: Optional[float] = None
    ) -> None:
        """
        Update order status from exchange.
        
        Args:
            order_id: Order ID to update
            status: New status
            filled_quantity: Amount filled
            average_fill_price: Average fill price
            fee: Fee paid
        """
        order = self._orders.get(order_id)
        if not order:
            logger.warning(f"Order {order_id} not found for update")
            return
        
        old_status = order.status
        order.status = status
        order.updated_at = datetime.utcnow()
        
        if filled_quantity is not None:
            order.filled_quantity = filled_quantity
        
        if average_fill_price is not None:
            order.average_fill_price = average_fill_price
        
        if fee is not None:
            order.fee = fee
            self._total_fees += fee
        
        level = self._get_level_for_order(order)
        if level:
            level.filled_quantity = order.filled_quantity
            level.last_fill_time = datetime.utcnow()
        
        if status == OrderStatus.FILLED and old_status != OrderStatus.FILLED:
            await self._handle_order_filled(order)
        
        logger.debug(f"Updated order {order_id}: {old_status.value} -> {status.value}")
    
    async def _handle_order_filled(self, order: GridOrder) -> None:
        """
        Handle a filled order - place counter order and calculate profit.
        
        Args:
            order: The filled order
        """
        self._filled_orders.append(order)
        self._trade_count += 1
        
        level = self._get_level_for_order(order)
        if level:
            level.is_active = False
        
        if order.side == GridSide.BUY:
            await self._place_counter_sell_order(order)
        elif order.side == GridSide.SELL:
            profit = self._calculate_profit(order)
            self._total_profit += profit
            await self._place_counter_buy_order(order)
        
        for callback in self._on_order_filled_callbacks:
            try:
                await callback(order)
            except Exception as e:
                logger.error(f"Order filled callback error: {e}")
        
        logger.info(
            f"Order filled: {order.side.value} {order.quantity} @ {order.price}, "
            f"total_profit={self._total_profit:.2f}"
        )
    
    async def _place_counter_sell_order(self, buy_order: GridOrder) -> Optional[GridOrder]:
        """
        Place a sell order after a buy order fills.
        
        The sell price is calculated to achieve the target profit per level.
        
        Args:
            buy_order: The filled buy order
            
        Returns:
            Created sell order or None
        """
        profit_multiplier = 1 + (self.grid_calculator.config.profit_per_level / 100)
        fee_multiplier = 1 + (self.grid_calculator.config.fee_percent / 100)
        
        sell_price = buy_order.price * profit_multiplier * fee_multiplier
        sell_price = round(sell_price, 2)
        
        sell_order = GridOrder(
            order_id=str(uuid.uuid4()),
            level_id=buy_order.level_id,
            symbol=buy_order.symbol,
            side=GridSide.SELL,
            order_type=OrderType.LIMIT,
            price=sell_price,
            quantity=buy_order.filled_quantity,
        )
        
        if self.paper_trading:
            sell_order.status = OrderStatus.OPEN
            sell_order.exchange_order_id = f"PAPER_{sell_order.order_id[:8]}"
        else:
            exchange_order = await self._place_exchange_order(sell_order)
            if exchange_order:
                sell_order.exchange_order_id = exchange_order.get("orderId")
                sell_order.status = OrderStatus.OPEN
            else:
                sell_order.status = OrderStatus.REJECTED
                return None
        
        self._orders[sell_order.order_id] = sell_order
        
        logger.info(
            f"Placed counter sell order at {sell_price} "
            f"(buy was at {buy_order.price})"
        )
        
        return sell_order
    
    async def _place_counter_buy_order(self, sell_order: GridOrder) -> Optional[GridOrder]:
        """
        Place a buy order after a sell order fills (reinvestment).
        
        Args:
            sell_order: The filled sell order
            
        Returns:
            Created buy order or None
        """
        level = self._get_level_for_order(sell_order)
        if level:
            return await self.place_order_for_level(level)
        
        return None
    
    def _calculate_profit(self, sell_order: GridOrder) -> float:
        """
        Calculate profit from a completed sell order.
        
        Args:
            sell_order: The filled sell order
            
        Returns:
            Profit amount in quote currency
        """
        buy_orders = [
            o for o in self._filled_orders
            if o.level_id == sell_order.level_id and o.side == GridSide.BUY
        ]
        
        if not buy_orders:
            return 0.0
        
        last_buy = buy_orders[-1]
        buy_cost = last_buy.filled_quantity * (last_buy.average_fill_price or last_buy.price)
        sell_revenue = sell_order.filled_quantity * (sell_order.average_fill_price or sell_order.price)
        
        profit = sell_revenue - buy_cost - last_buy.fee - sell_order.fee
        
        return profit
    
    def _get_level_for_order(self, order: GridOrder) -> Optional[GridLevel]:
        """Get the grid level associated with an order."""
        for level in self.grid_calculator.levels:
            if level.level_id == order.level_id:
                return level
        return None
    
    async def simulate_fill(self, order_id: str, fill_price: Optional[float] = None) -> bool:
        """
        Simulate an order fill (for paper trading).
        
        Args:
            order_id: Order ID to fill
            fill_price: Price at which to fill (defaults to order price)
            
        Returns:
            True if simulated successfully
        """
        order = self._orders.get(order_id)
        if not order:
            return False
        
        if not order.is_active:
            return False
        
        fee = order.quantity * (fill_price or order.price) * (self.grid_calculator.config.fee_percent / 100)
        
        await self.update_order_status(
            order_id=order_id,
            status=OrderStatus.FILLED,
            filled_quantity=order.quantity,
            average_fill_price=fill_price or order.price,
            fee=fee,
        )
        
        return True
    
    async def check_fills_at_price(self, current_price: float) -> List[GridOrder]:
        """
        Check if any orders should be filled at the current price.
        
        For paper trading, this simulates order fills when price
        crosses order levels.
        
        Args:
            current_price: Current market price
            
        Returns:
            List of orders that were filled
        """
        filled_orders = []
        
        for order in list(self.active_orders):
            should_fill = False
            
            if order.side == GridSide.BUY and current_price <= order.price:
                should_fill = True
            elif order.side == GridSide.SELL and current_price >= order.price:
                should_fill = True
            
            if should_fill:
                if await self.simulate_fill(order.order_id, current_price):
                    filled_orders.append(order)
        
        return filled_orders
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get order manager status.
        
        Returns:
            Dictionary with status information
        """
        return {
            "symbol": self.grid_calculator.config.symbol,
            "paper_trading": self.paper_trading,
            "total_orders": len(self._orders),
            "active_orders": len(self.active_orders),
            "active_buy_orders": len([o for o in self.active_orders if o.side == GridSide.BUY]),
            "active_sell_orders": len([o for o in self.active_orders if o.side == GridSide.SELL]),
            "filled_orders": len(self._filled_orders),
            "trade_count": self._trade_count,
            "total_profit": round(self._total_profit, 2),
            "total_fees": round(self._total_fees, 4),
            "net_profit": round(self._total_profit - self._total_fees, 2),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert order manager state to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            "status": self.get_status(),
            "orders": [o.to_dict() for o in self._orders.values()],
            "filled_orders": [o.to_dict() for o in self._filled_orders],
        }
