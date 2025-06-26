from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

from autobot.trading.order import Order, OrderSide

class Position:
    """
    Represents a trading position with associated orders and P&L tracking.
    """
    def __init__(
        self,
        symbol: str,
        side: OrderSide,
        entry_price: float,
        amount: float,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        leverage: float = 1.0
    ):
        self.id = str(uuid.uuid4())
        self.symbol = symbol
        self.side = side
        self.entry_price = entry_price
        self.amount = amount
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.leverage = leverage
        self.created_at = datetime.now()
        self.updated_at = self.created_at
        self.exit_price = None
        self.exit_time = None
        self.is_open = True
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.orders: List[Order] = []
        
    def add_order(self, order: Order):
        """
        Add an order to this position.
        """
        self.orders.append(order)
        self.updated_at = datetime.now()
    
    def close(self, exit_price: float, exit_time: Optional[datetime] = None):
        """
        Close the position and calculate realized P&L.
        """
        self.exit_price = exit_price
        self.exit_time = exit_time or datetime.now()
        self.is_open = False
        self.updated_at = self.exit_time
        
        if self.side == OrderSide.BUY:
            self.realized_pnl = (exit_price - self.entry_price) * self.amount * self.leverage
        else:
            self.realized_pnl = (self.entry_price - exit_price) * self.amount * self.leverage
    
    def update_unrealized_pnl(self, current_price: float):
        """
        Update the unrealized P&L based on current market price.
        """
        if not self.is_open:
            return
            
        if self.side == OrderSide.BUY:
            self.unrealized_pnl = (current_price - self.entry_price) * self.amount * self.leverage
        else:
            self.unrealized_pnl = (self.entry_price - current_price) * self.amount * self.leverage
        
        self.updated_at = datetime.now()
    
    def should_close(self, current_price: float) -> bool:
        """
        Check if the position should be closed based on take profit or stop loss.
        """
        if not self.is_open:
            return False
            
        if self.side == OrderSide.BUY:
            if self.take_profit and current_price >= self.take_profit:
                return True
            if self.stop_loss and current_price <= self.stop_loss:
                return True
        else:
            if self.take_profit and current_price <= self.take_profit:
                return True
            if self.stop_loss and current_price >= self.stop_loss:
                return True
                
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert position to dictionary for serialization.
        """
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "amount": self.amount,
            "take_profit": self.take_profit,
            "stop_loss": self.stop_loss,
            "leverage": self.leverage,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "exit_price": self.exit_price,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "is_open": self.is_open,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "orders": [order.to_dict() for order in self.orders]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """
        Create position from dictionary.
        """
        from autobot.trading.order import Order
        
        position = cls(
            symbol=data["symbol"],
            side=OrderSide(data["side"]),
            entry_price=data["entry_price"],
            amount=data["amount"],
            take_profit=data.get("take_profit"),
            stop_loss=data.get("stop_loss"),
            leverage=data.get("leverage", 1.0)
        )
        
        position.id = data["id"]
        position.created_at = datetime.fromisoformat(data["created_at"])
        position.updated_at = datetime.fromisoformat(data["updated_at"])
        position.exit_price = data.get("exit_price")
        
        if data.get("exit_time"):
            position.exit_time = datetime.fromisoformat(data["exit_time"])
            
        position.is_open = data["is_open"]
        position.realized_pnl = data["realized_pnl"]
        position.unrealized_pnl = data["unrealized_pnl"]
        
        if "orders" in data:
            position.orders = [Order.from_dict(order_data) for order_data in data["orders"]]
            
        return position
