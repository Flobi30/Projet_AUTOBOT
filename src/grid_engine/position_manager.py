"""
Position Manager Module for AUTOBOT Grid Trading Engine.

Detects when buy orders are filled on the exchange and automatically
places sell orders at the corresponding upper grid level.

Cycle: BUY filled -> calculate sell level -> place SELL LIMIT

Uses:
- grid_calculator.py for grid level prices
- order_manager.py for order placement
- Kraken API (via ccxt) for order status queries
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable

from .grid_calculator import GridCalculator, GridLevel, GridSide
from .order_manager import GridOrderManager, GridOrder, OrderStatus, OrderType

logger = logging.getLogger(__name__)

SELL_LEVEL_OFFSET = 8
DEFAULT_POLL_INTERVAL = 5
DEFAULT_PROFIT_TARGET = 0.8


class PositionStatus(Enum):
    """Status of a grid position through its lifecycle."""
    WAITING_BUY_FILL = "waiting_buy_fill"
    BUY_FILLED = "buy_filled"
    SELL_PLACED = "sell_placed"
    SELL_FILLED = "sell_filled"
    CLOSED = "closed"
    ERROR = "error"


@dataclass
class ManagedPosition:
    """
    Represents a managed position in the grid trading cycle.

    Tracks the full lifecycle: BUY order placed -> BUY filled ->
    SELL order placed -> SELL filled -> position closed.

    Attributes:
        position_id: Unique position identifier
        buy_level_id: Grid level ID of the buy order (0-6)
        sell_level_id: Grid level ID of the sell order (8-14)
        buy_order_id: Internal order ID for the buy
        sell_order_id: Internal order ID for the sell
        buy_exchange_id: Exchange order ID for the buy
        sell_exchange_id: Exchange order ID for the sell
        buy_price: Actual fill price of the buy
        sell_price: Target sell price
        volume: Position volume
        status: Current position status
        profit_amount: Realized or expected profit
        profit_percent: Profit as percentage
        buy_filled_at: Timestamp when buy was filled
        sell_placed_at: Timestamp when sell was placed
        sell_filled_at: Timestamp when sell was filled
        created_at: Position creation timestamp
    """
    position_id: str
    buy_level_id: int
    sell_level_id: int
    buy_order_id: str
    buy_price: float
    volume: float
    sell_order_id: Optional[str] = None
    buy_exchange_id: Optional[str] = None
    sell_exchange_id: Optional[str] = None
    sell_price: Optional[float] = None
    status: PositionStatus = PositionStatus.WAITING_BUY_FILL
    profit_amount: float = 0.0
    profit_percent: float = 0.0
    buy_filled_at: Optional[datetime] = None
    sell_placed_at: Optional[datetime] = None
    sell_filled_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_active(self) -> bool:
        """Check if position is still active (not closed or errored)."""
        return self.status not in (PositionStatus.CLOSED, PositionStatus.ERROR)

    @property
    def expected_profit(self) -> float:
        """Calculate expected profit based on buy and sell prices."""
        if self.sell_price is None:
            return 0.0
        return (self.sell_price - self.buy_price) * self.volume

    @property
    def expected_profit_pct(self) -> float:
        """Calculate expected profit percentage."""
        if self.buy_price == 0:
            return 0.0
        if self.sell_price is None:
            return 0.0
        return ((self.sell_price - self.buy_price) / self.buy_price) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert position to dictionary."""
        return {
            "position_id": self.position_id,
            "buy_level_id": self.buy_level_id,
            "sell_level_id": self.sell_level_id,
            "buy_order_id": self.buy_order_id,
            "sell_order_id": self.sell_order_id,
            "buy_exchange_id": self.buy_exchange_id,
            "sell_exchange_id": self.sell_exchange_id,
            "buy_price": self.buy_price,
            "sell_price": self.sell_price,
            "volume": self.volume,
            "status": self.status.value,
            "profit_amount": round(self.profit_amount, 4),
            "profit_percent": round(self.profit_percent, 4),
            "expected_profit": round(self.expected_profit, 4),
            "expected_profit_pct": round(self.expected_profit_pct, 2),
            "buy_filled_at": self.buy_filled_at.isoformat() if self.buy_filled_at else None,
            "sell_placed_at": self.sell_placed_at.isoformat() if self.sell_placed_at else None,
            "sell_filled_at": self.sell_filled_at.isoformat() if self.sell_filled_at else None,
            "created_at": self.created_at.isoformat(),
        }


class GridPositionManager:
    """
    Manages the full lifecycle of grid trading positions.

    Monitors buy orders, detects fills, calculates sell prices,
    and places corresponding sell orders at upper grid levels.

    Grid mapping (15 levels, offset=8):
        BUY Level 0 -> SELL Level 8
        BUY Level 1 -> SELL Level 9
        BUY Level 2 -> SELL Level 10
        ...
        BUY Level 6 -> SELL Level 14

    Example:
        calculator = GridCalculator(config)
        levels = calculator.calculate_grid(53000.0)
        order_manager = GridOrderManager(calculator)

        position_manager = GridPositionManager(
            grid_calculator=calculator,
            order_manager=order_manager,
        )

        # Start monitoring buy orders for fills
        await position_manager.check_and_process_fills()
    """

    def __init__(
        self,
        grid_calculator: GridCalculator,
        order_manager: GridOrderManager,
        sell_level_offset: int = SELL_LEVEL_OFFSET,
        profit_target_pct: float = DEFAULT_PROFIT_TARGET,
        exchange_client: Optional[Any] = None,
    ):
        """
        Initialize position manager.

        Args:
            grid_calculator: GridCalculator with calculated levels
            order_manager: GridOrderManager for order operations
            sell_level_offset: Offset between buy and sell levels (default: 8)
            profit_target_pct: Minimum profit target percentage (default: 0.8%)
            exchange_client: Exchange client for direct API calls (optional)
        """
        self.grid_calculator = grid_calculator
        self.order_manager = order_manager
        self.sell_level_offset = sell_level_offset
        self.profit_target_pct = profit_target_pct
        self.exchange_client = exchange_client

        self._positions: Dict[str, ManagedPosition] = {}
        self._completed_positions: List[ManagedPosition] = []
        self._total_realized_profit: float = 0.0
        self._total_cycles: int = 0

        self._on_buy_filled_callbacks: List[Callable] = []
        self._on_sell_placed_callbacks: List[Callable] = []
        self._on_cycle_complete_callbacks: List[Callable] = []

        logger.info(
            f"GridPositionManager initialized | "
            f"sell_offset={sell_level_offset} | "
            f"profit_target={profit_target_pct}%"
        )

    @property
    def positions(self) -> Dict[str, ManagedPosition]:
        """Get all active positions."""
        return self._positions

    @property
    def active_positions(self) -> List[ManagedPosition]:
        """Get positions that are still active."""
        return [p for p in self._positions.values() if p.is_active]

    @property
    def completed_positions(self) -> List[ManagedPosition]:
        """Get all completed positions."""
        return self._completed_positions

    @property
    def total_realized_profit(self) -> float:
        """Get total realized profit from completed cycles."""
        return self._total_realized_profit

    @property
    def total_cycles(self) -> int:
        """Get total number of completed buy->sell cycles."""
        return self._total_cycles

    def on_buy_filled(self, callback: Callable) -> None:
        """Register callback for buy order filled events."""
        self._on_buy_filled_callbacks.append(callback)

    def on_sell_placed(self, callback: Callable) -> None:
        """Register callback for sell order placed events."""
        self._on_sell_placed_callbacks.append(callback)

    def on_cycle_complete(self, callback: Callable) -> None:
        """Register callback for completed buy->sell cycle events."""
        self._on_cycle_complete_callbacks.append(callback)

    def get_sell_level_for_buy(self, buy_level_id: int) -> Optional[GridLevel]:
        """
        Get the sell level corresponding to a buy level.

        Mapping: BUY Level N -> SELL Level (N + sell_level_offset)

        Args:
            buy_level_id: Buy level ID (0-6 for 15-level grid)

        Returns:
            Sell GridLevel or None if out of bounds
        """
        sell_level_id = buy_level_id + self.sell_level_offset
        levels = self.grid_calculator.levels

        if sell_level_id >= len(levels):
            logger.warning(
                f"Sell level {sell_level_id} out of bounds "
                f"(max: {len(levels) - 1}) for buy level {buy_level_id}"
            )
            return None

        sell_level = levels[sell_level_id]

        if sell_level.side != GridSide.SELL:
            logger.warning(
                f"Level {sell_level_id} is not a SELL level "
                f"(side: {sell_level.side.value})"
            )
            return None

        return sell_level

    def calculate_sell_price(
        self, buy_price: float, sell_level: GridLevel
    ) -> float:
        """
        Calculate the optimal sell price.

        Uses the grid sell level price, with a minimum profit target
        above the buy price.

        Args:
            buy_price: Actual buy fill price
            sell_level: Target sell grid level

        Returns:
            Sell price
        """
        grid_sell_price = sell_level.price
        min_sell_price = buy_price * (1 + self.profit_target_pct / 100)
        return max(grid_sell_price, min_sell_price)

    async def check_and_process_fills(self) -> List[ManagedPosition]:
        """
        Check all active buy orders for fills and process them.

        For each filled buy order:
        1. Detect the fill
        2. Calculate sell level and price
        3. Place sell order
        4. Create/update ManagedPosition

        Returns:
            List of positions that had sells placed this cycle
        """
        processed: List[ManagedPosition] = []
        buy_orders = self.order_manager.buy_orders

        for order in buy_orders:
            if order.status != OrderStatus.FILLED:
                continue

            if self._is_order_already_managed(order.order_id):
                continue

            position = await self._process_filled_buy(order)
            if position is not None:
                processed.append(position)

        return processed

    def _is_order_already_managed(self, order_id: str) -> bool:
        """Check if a buy order already has a managed position."""
        for pos in self._positions.values():
            if pos.buy_order_id == order_id:
                return True
        for pos in self._completed_positions:
            if pos.buy_order_id == order_id:
                return True
        return False

    async def _process_filled_buy(self, buy_order: GridOrder) -> Optional[ManagedPosition]:
        """
        Process a filled buy order: calculate sell and place order.

        Args:
            buy_order: The filled buy GridOrder

        Returns:
            ManagedPosition with sell placed, or None on failure
        """
        buy_price = buy_order.average_fill_price or buy_order.price
        volume = buy_order.filled_quantity

        logger.info(
            f"Buy order filled: Level {buy_order.level_id} | "
            f"Price: {buy_price:.2f} | Volume: {volume:.8f}"
        )

        sell_level = self.get_sell_level_for_buy(buy_order.level_id)
        if sell_level is None:
            logger.error(
                f"No sell level found for buy level {buy_order.level_id}"
            )
            return None

        sell_price = self.calculate_sell_price(buy_price, sell_level)

        position = ManagedPosition(
            position_id=f"POS-{buy_order.level_id}-{int(datetime.utcnow().timestamp())}",
            buy_level_id=buy_order.level_id,
            sell_level_id=sell_level.level_id,
            buy_order_id=buy_order.order_id,
            buy_exchange_id=buy_order.exchange_order_id,
            buy_price=buy_price,
            volume=volume,
            sell_price=sell_price,
            status=PositionStatus.BUY_FILLED,
            buy_filled_at=datetime.utcnow(),
        )

        for callback in self._on_buy_filled_callbacks:
            try:
                await callback(position)
            except Exception as e:
                logger.error(f"Buy filled callback error: {e}")

        sell_order = await self._place_sell_for_position(position, sell_level)

        if sell_order is None:
            position.status = PositionStatus.ERROR
            self._positions[position.position_id] = position
            return None

        position.sell_order_id = sell_order.order_id
        position.sell_exchange_id = sell_order.exchange_order_id
        position.status = PositionStatus.SELL_PLACED
        position.sell_placed_at = datetime.utcnow()
        position.profit_amount = position.expected_profit
        position.profit_percent = position.expected_profit_pct

        self._positions[position.position_id] = position

        for callback in self._on_sell_placed_callbacks:
            try:
                await callback(position)
            except Exception as e:
                logger.error(f"Sell placed callback error: {e}")

        logger.info(
            f"Cycle started: BUY L{buy_order.level_id} @ {buy_price:.2f} "
            f"-> SELL L{sell_level.level_id} @ {sell_price:.2f} | "
            f"Expected profit: {position.expected_profit:.4f} "
            f"({position.expected_profit_pct:.2f}%)"
        )

        return position

    async def _place_sell_for_position(
        self, position: ManagedPosition, sell_level: GridLevel
    ) -> Optional[GridOrder]:
        """
        Place a sell order for a position.

        Args:
            position: The managed position
            sell_level: Grid level for the sell

        Returns:
            Created sell GridOrder or None on failure
        """
        sell_order = GridOrder(
            order_id=f"SELL-{position.buy_level_id}-{int(datetime.utcnow().timestamp())}",
            level_id=sell_level.level_id,
            symbol=self.grid_calculator.config.symbol,
            side=GridSide.SELL,
            order_type=OrderType.LIMIT,
            price=position.sell_price or sell_level.price,
            quantity=position.volume,
        )

        if self.order_manager.paper_trading:
            sell_order.status = OrderStatus.OPEN
            sell_order.exchange_order_id = f"PAPER_{sell_order.order_id[:8]}"
        else:
            try:
                exchange_result = await self.order_manager._place_exchange_order(sell_order)
                if exchange_result:
                    sell_order.exchange_order_id = exchange_result.get("orderId")
                    sell_order.status = OrderStatus.OPEN
                else:
                    sell_order.status = OrderStatus.REJECTED
                    logger.error(
                        f"Failed to place sell order for level {sell_level.level_id}"
                    )
                    return None
            except Exception as e:
                logger.error(f"Exchange error placing sell order: {e}")
                return None

        self.order_manager._orders[sell_order.order_id] = sell_order

        logger.info(
            f"Sell order placed: {sell_order.order_id} | "
            f"Level {sell_level.level_id} @ {sell_order.price:.2f} | "
            f"Volume: {sell_order.quantity:.8f}"
        )

        return sell_order

    async def check_sell_fills(self) -> List[ManagedPosition]:
        """
        Check if any sell orders have been filled, completing the cycle.

        Returns:
            List of positions whose sell orders were filled
        """
        completed: List[ManagedPosition] = []

        for position in list(self.active_positions):
            if position.status != PositionStatus.SELL_PLACED:
                continue

            if position.sell_order_id is None:
                continue

            sell_order = self.order_manager.orders.get(position.sell_order_id)
            if sell_order is None:
                continue

            if sell_order.status == OrderStatus.FILLED:
                position.status = PositionStatus.CLOSED
                position.sell_filled_at = datetime.utcnow()

                actual_sell_price = sell_order.average_fill_price or sell_order.price
                position.profit_amount = (actual_sell_price - position.buy_price) * position.volume
                position.profit_percent = (
                    (actual_sell_price - position.buy_price) / position.buy_price
                ) * 100

                self._total_realized_profit += position.profit_amount
                self._total_cycles += 1

                self._completed_positions.append(position)

                for callback in self._on_cycle_complete_callbacks:
                    try:
                        await callback(position)
                    except Exception as e:
                        logger.error(f"Cycle complete callback error: {e}")

                logger.info(
                    f"Cycle COMPLETE: {position.position_id} | "
                    f"Profit: {position.profit_amount:.4f} ({position.profit_percent:.2f}%) | "
                    f"Total cycles: {self._total_cycles}"
                )

                completed.append(position)

        return completed

    async def run_cycle(self) -> Dict[str, Any]:
        """
        Run one full monitoring cycle: check buy fills + check sell fills.

        Returns:
            Dict with cycle results
        """
        new_sells = await self.check_and_process_fills()
        completed = await self.check_sell_fills()

        return {
            "new_sell_orders": len(new_sells),
            "completed_cycles": len(completed),
            "active_positions": len(self.active_positions),
            "total_cycles": self._total_cycles,
            "total_profit": round(self._total_realized_profit, 4),
        }

    def get_grid_mapping(self) -> List[Dict[str, Any]]:
        """
        Get the complete BUY -> SELL level mapping.

        Returns:
            List of dicts with buy/sell level info and spread
        """
        mapping = []
        for level in self.grid_calculator.levels:
            if level.side != GridSide.BUY:
                continue

            sell_level = self.get_sell_level_for_buy(level.level_id)
            if sell_level is None:
                continue

            spread = sell_level.price - level.price
            spread_pct = (spread / level.price) * 100 if level.price > 0 else 0

            mapping.append({
                "buy_level_id": level.level_id,
                "buy_price": level.price,
                "sell_level_id": sell_level.level_id,
                "sell_price": sell_level.price,
                "spread": round(spread, 2),
                "spread_pct": round(spread_pct, 2),
            })

        return mapping

    def get_status(self) -> Dict[str, Any]:
        """Get position manager status."""
        active = self.active_positions
        waiting = [p for p in active if p.status == PositionStatus.WAITING_BUY_FILL]
        sell_placed = [p for p in active if p.status == PositionStatus.SELL_PLACED]
        errors = [p for p in self._positions.values() if p.status == PositionStatus.ERROR]

        return {
            "total_positions": len(self._positions),
            "active_positions": len(active),
            "waiting_buy_fill": len(waiting),
            "sell_placed": len(sell_placed),
            "completed_cycles": self._total_cycles,
            "error_positions": len(errors),
            "total_realized_profit": round(self._total_realized_profit, 4),
            "sell_level_offset": self.sell_level_offset,
            "profit_target_pct": self.profit_target_pct,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert position manager state to dictionary."""
        return {
            "status": self.get_status(),
            "grid_mapping": self.get_grid_mapping(),
            "active_positions": [p.to_dict() for p in self.active_positions],
            "completed_positions": [
                p.to_dict() for p in self._completed_positions[-50:]
            ],
        }
