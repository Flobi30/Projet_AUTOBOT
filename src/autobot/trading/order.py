from enum import Enum
from typing import Optional
from datetime import datetime
import uuid

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"

class OrderStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"

class Order:
    """
    Represents a trading order with all necessary parameters.
    """
    def __init__(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        amount: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        time_in_force: str = "GTC"  # Good Till Canceled
    ):
        self.id = str(uuid.uuid4())
        self.symbol = symbol
        self.order_type = order_type
        self.side = side
        self.amount = amount
        self.price = price
        self.stop_price = stop_price
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.time_in_force = time_in_force
        self.status = OrderStatus.PENDING
        self.created_at = datetime.now()
        self.updated_at = self.created_at
        self.filled_amount = 0.0
        self.remaining_amount = amount
        self.average_price = None
        self.cost = 0.0
        self.fee = 0.0
        
    def update_status(self, status: OrderStatus, filled_amount: float = None, 
                     average_price: float = None, cost: float = None, fee: float = None):
        """
        Update the order status and fill information.
        """
        self.status = status
        self.updated_at = datetime.now()
        
        if filled_amount is not None:
            self.filled_amount = filled_amount
            self.remaining_amount = max(0, self.amount - filled_amount)
            
        if average_price is not None:
            self.average_price = average_price
            
        if cost is not None:
            self.cost = cost
            
        if fee is not None:
            self.fee = fee
    
    def is_active(self) -> bool:
        """
        Check if the order is still active.
        """
        return self.status in [OrderStatus.PENDING, OrderStatus.OPEN]
    
    def is_filled(self) -> bool:
        """
        Check if the order is completely filled.
        """
        return self.status == OrderStatus.FILLED
    
    def to_dict(self):
        """
        Convert order to dictionary for serialization.
        """
        return {
            "id": self.id,
            "symbol": self.symbol,
            "order_type": self.order_type.value,
            "side": self.side.value,
            "amount": self.amount,
            "price": self.price,
            "stop_price": self.stop_price,
            "take_profit": self.take_profit,
            "stop_loss": self.stop_loss,
            "time_in_force": self.time_in_force,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "filled_amount": self.filled_amount,
            "remaining_amount": self.remaining_amount,
            "average_price": self.average_price,
            "cost": self.cost,
            "fee": self.fee
        }
    
    @classmethod
    def from_dict(cls, data):
        """
        Create an order from dictionary.
        """
        order = cls(
            symbol=data["symbol"],
            order_type=OrderType(data["order_type"]),
            side=OrderSide(data["side"]),
            amount=data["amount"],
            price=data.get("price"),
            stop_price=data.get("stop_price"),
            take_profit=data.get("take_profit"),
            stop_loss=data.get("stop_loss"),
            time_in_force=data.get("time_in_force", "GTC")
        )
        
        order.id = data["id"]
        order.status = OrderStatus(data["status"])
        order.created_at = datetime.fromisoformat(data["created_at"])
        order.updated_at = datetime.fromisoformat(data["updated_at"])
        order.filled_amount = data["filled_amount"]
        order.remaining_amount = data["remaining_amount"]
        order.average_price = data.get("average_price")
        order.cost = data.get("cost", 0.0)
        order.fee = data.get("fee", 0.0)
        
        return order
