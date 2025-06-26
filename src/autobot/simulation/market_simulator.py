"""
Market Simulator for AUTOBOT.
Provides a realistic market simulation environment for backtesting trading strategies.
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Union, Callable, Tuple
from datetime import datetime, timedelta
import json
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import random

from ..trading.order import Order, OrderType, OrderSide
from ..trading.position import Position
from ..trading.execution import ExecutionResult

logger = logging.getLogger(__name__)

class MarketCondition:
    """Market condition enum for simulation."""
    NORMAL = "normal"
    VOLATILE = "volatile"
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    SIDEWAYS = "sideways"
    FLASH_CRASH = "flash_crash"
    RECOVERY = "recovery"

class MarketEvent:
    """Market event for simulation."""
    
    def __init__(
        self,
        event_type: str,
        timestamp: datetime,
        impact: float,
        duration: timedelta,
        affected_symbols: List[str] = None,
        description: str = ""
    ):
        """
        Initialize a market event.
        
        Args:
            event_type: Type of event
            timestamp: Event timestamp
            impact: Impact factor (-1.0 to 1.0)
            duration: Event duration
            affected_symbols: Affected symbols
            description: Event description
        """
        self.event_type = event_type
        self.timestamp = timestamp
        self.impact = impact
        self.duration = duration
        self.affected_symbols = affected_symbols or []
        self.description = description
        self.is_active = False
    
    def is_applicable(self, timestamp: datetime, symbol: str) -> bool:
        """
        Check if the event is applicable at the given timestamp for the symbol.
        
        Args:
            timestamp: Current timestamp
            symbol: Symbol to check
            
        Returns:
            True if applicable, False otherwise
        """
        if not self.is_active:
            return False
        
        if self.timestamp > timestamp:
            return False
        
        if timestamp > self.timestamp + self.duration:
            return False
        
        if self.affected_symbols and symbol not in self.affected_symbols:
            return False
        
        return True
    
    def get_price_impact(self, base_price: float) -> float:
        """
        Get the price impact of the event.
        
        Args:
            base_price: Base price
            
        Returns:
            Price impact
        """
        return base_price * self.impact
    
    def activate(self):
        """Activate the event."""
        self.is_active = True
    
    def deactivate(self):
        """Deactivate the event."""
        self.is_active = False

class MarketSimulator:
    """
    Realistic market simulator for backtesting trading strategies.
    Simulates market conditions, order execution, slippage, and market impact.
    """
    
    def __init__(
        self,
        data: Optional[pd.DataFrame] = None,
        config: Dict[str, Any] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        symbols: List[str] = None,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.001,
        slippage_model: str = "fixed",
        slippage_factor: float = 0.0005,
        market_impact_factor: float = 0.0001,
        tick_size: float = 0.01,
        random_seed: Optional[int] = None
    ):
        """
        Initialize the market simulator.
        
        Args:
            data: Historical market data
            config: Configuration dictionary
            start_date: Simulation start date
            end_date: Simulation end date
            symbols: Symbols to simulate
            initial_capital: Initial capital
            commission_rate: Commission rate
            slippage_model: Slippage model (fixed, normal, pareto)
            slippage_factor: Slippage factor
            market_impact_factor: Market impact factor
            tick_size: Tick size
            random_seed: Random seed
        """
        self.config = config or {}
        self.data = data
        self.start_date = start_date
        self.end_date = end_date
        self.symbols = symbols or []
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_model = slippage_model
        self.slippage_factor = slippage_factor
        self.market_impact_factor = market_impact_factor
        self.tick_size = tick_size
        
        if random_seed is not None:
            random.seed(random_seed)
            np.random.seed(random_seed)
        
        self.current_timestamp = None
        self.current_prices = {}
        self.current_volumes = {}
        self.current_capital = initial_capital
        self.positions = {}
        self.orders = []
        self.executed_orders = []
        self.market_events = []
        self.market_condition = MarketCondition.NORMAL
        
        self.performance_metrics = {
            "portfolio_value": [],
            "returns": [],
            "drawdowns": [],
            "sharpe_ratio": None,
            "max_drawdown": None,
            "total_return": None,
            "win_rate": None
        }
        
        self.is_initialized = False
    
    def initialize(self):
        """Initialize the simulator."""
        if self.is_initialized:
            return
        
        logger.info("Initializing market simulator")
        
        if self.data is None:
            raise ValueError("Market data is required")
        
        if self.start_date is None:
            self.start_date = self.data.index[0]
        
        if self.end_date is None:
            self.end_date = self.data.index[-1]
        
        self.data = self.data[(self.data.index >= self.start_date) & (self.data.index <= self.end_date)]
        
        if not self.symbols:
            unique_prefixes = set()
            for col in self.data.columns:
                if "_" in col:
                    prefix = col.split("_")[0]
                    unique_prefixes.add(prefix)
            
            self.symbols = list(unique_prefixes)
        
        self.current_timestamp = self.start_date
        
        for symbol in self.symbols:
            self.positions[symbol] = Position(symbol, 0, 0.0)
        
        self._generate_market_events()
        
        self.is_initialized = True
        
        logger.info(f"Market simulator initialized with {len(self.symbols)} symbols and {len(self.data)} data points")
    
    def _generate_market_events(self):
        """Generate random market events for the simulation period."""
        num_events = int((self.end_date - self.start_date).days / 30)  # Roughly one event per month
        
        event_types = [
            "earnings_report",
            "economic_data",
            "central_bank_announcement",
            "geopolitical_event",
            "natural_disaster",
            "regulatory_change",
            "merger_acquisition",
            "product_launch",
            "scandal",
            "market_sentiment_shift"
        ]
        
        for _ in range(num_events):
            days_offset = random.randint(0, (self.end_date - self.start_date).days)
            timestamp = self.start_date + timedelta(days=days_offset)
            
            event_type = random.choice(event_types)
            
            impact = (random.random() - 0.5) * 0.2
            
            duration = timedelta(days=random.randint(1, 10))
            
            if random.random() < 0.5:
                affected_symbols = self.symbols
            else:
                num_affected = random.randint(1, min(3, len(self.symbols)))
                affected_symbols = random.sample(self.symbols, num_affected)
            
            event = MarketEvent(
                event_type=event_type,
                timestamp=timestamp,
                impact=impact,
                duration=duration,
                affected_symbols=affected_symbols,
                description=f"{event_type.replace('_', ' ').title()} affecting {', '.join(affected_symbols)}"
            )
            
            self.market_events.append(event)
        
        logger.info(f"Generated {len(self.market_events)} market events")
    
    def _update_market_condition(self):
        """Update the current market condition based on recent price movements."""
        recent_data = self.data[self.data.index <= self.current_timestamp].tail(20)
        
        if len(recent_data) < 5:
            return
        
        volatilities = []
        trends = []
        
        for symbol in self.symbols:
            price_col = f"{symbol}_close"
            
            if price_col not in recent_data.columns:
                continue
            
            prices = recent_data[price_col].values
            
            returns = np.diff(prices) / prices[:-1]
            
            volatility = np.std(returns)
            volatilities.append(volatility)
            
            trend = np.mean(returns)
            trends.append(trend)
        
        avg_volatility = np.mean(volatilities) if volatilities else 0
        avg_trend = np.mean(trends) if trends else 0
        
        if avg_volatility > 0.02:  # High volatility
            self.market_condition = MarketCondition.VOLATILE
        elif avg_trend > 0.01:  # Strong uptrend
            self.market_condition = MarketCondition.TRENDING_UP
        elif avg_trend < -0.01:  # Strong downtrend
            self.market_condition = MarketCondition.TRENDING_DOWN
        elif abs(avg_trend) < 0.002 and avg_volatility < 0.01:  # Low volatility and no trend
            self.market_condition = MarketCondition.SIDEWAYS
        else:
            self.market_condition = MarketCondition.NORMAL
        
        for event in self.market_events:
            if event.is_applicable(self.current_timestamp, self.symbols[0]):
                if event.event_type == "natural_disaster" and event.impact < -0.05:
                    self.market_condition = MarketCondition.FLASH_CRASH
                elif event.event_type == "market_sentiment_shift" and event.impact > 0.05:
                    self.market_condition = MarketCondition.RECOVERY
    
    def _update_current_prices(self):
        """Update current prices based on the current timestamp."""
        current_data = self.data[self.data.index == self.current_timestamp]
        
        if current_data.empty:
            current_data = self.data[self.data.index <= self.current_timestamp].tail(1)
        
        if current_data.empty:
            logger.warning(f"No data available for timestamp {self.current_timestamp}")
            return
        
        for symbol in self.symbols:
            open_col = f"{symbol}_open"
            high_col = f"{symbol}_high"
            low_col = f"{symbol}_low"
            close_col = f"{symbol}_close"
            volume_col = f"{symbol}_volume"
            
            if close_col in current_data.columns:
                self.current_prices[symbol] = {
                    "open": current_data[open_col].iloc[0] if open_col in current_data.columns else None,
                    "high": current_data[high_col].iloc[0] if high_col in current_data.columns else None,
                    "low": current_data[low_col].iloc[0] if low_col in current_data.columns else None,
                    "close": current_data[close_col].iloc[0]
                }
            
            if volume_col in current_data.columns:
                self.current_volumes[symbol] = current_data[volume_col].iloc[0]
    
    def _apply_market_events(self):
        """Apply active market events to current prices."""
        for event in self.market_events:
            for symbol in self.symbols:
                if event.is_applicable(self.current_timestamp, symbol):
                    if symbol in self.current_prices:
                        for price_type in ["open", "high", "low", "close"]:
                            if self.current_prices[symbol][price_type] is not None:
                                impact = event.get_price_impact(self.current_prices[symbol][price_type])
                                self.current_prices[symbol][price_type] += impact
    
    def _calculate_slippage(self, order: Order) -> float:
        """
        Calculate slippage for an order.
        
        Args:
            order: Order
            
        Returns:
            Slippage amount
        """
        if self.slippage_model == "fixed":
            return order.price * self.slippage_factor
        
        elif self.slippage_model == "normal":
            mean_slippage = order.price * self.slippage_factor
            std_dev = mean_slippage * 0.5
            return np.random.normal(mean_slippage, std_dev)
        
        elif self.slippage_model == "pareto":
            shape = 3.0  # Shape parameter
            scale = order.price * self.slippage_factor
            return np.random.pareto(shape) * scale
        
        else:
            return 0.0
    
    def _calculate_market_impact(self, order: Order) -> float:
        """
        Calculate market impact for an order.
        
        Args:
            order: Order
            
        Returns:
            Market impact amount
        """
        if order.symbol not in self.current_volumes:
            return 0.0
        
        volume = self.current_volumes[order.symbol]
        
        if volume == 0:
            return 0.0
        
        relative_size = (order.quantity * order.price) / (volume * order.price)
        
        return order.price * self.market_impact_factor * np.sqrt(relative_size)
    
    def _execute_order(self, order: Order) -> ExecutionResult:
        """
        Execute an order.
        
        Args:
            order: Order to execute
            
        Returns:
            Execution result
        """
        if order.symbol not in self.current_prices:
            return ExecutionResult(
                order_id=order.order_id,
                symbol=order.symbol,
                quantity=0,
                price=0.0,
                timestamp=self.current_timestamp,
                status="failed",
                message=f"No price data for {order.symbol}"
            )
        
        if order.order_type == OrderType.MARKET:
            base_price = self.current_prices[order.symbol]["close"]
        else:
            base_price = order.price
        
        slippage = self._calculate_slippage(order)
        
        market_impact = self._calculate_market_impact(order)
        
        if order.side == OrderSide.BUY:
            execution_price = base_price + slippage + market_impact
        else:
            execution_price = base_price - slippage - market_impact
        
        execution_price = round(execution_price / self.tick_size) * self.tick_size
        
        if order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY and execution_price > order.price:
                return ExecutionResult(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    quantity=0,
                    price=0.0,
                    timestamp=self.current_timestamp,
                    status="pending",
                    message=f"Limit buy price {order.price} below execution price {execution_price}"
                )
            
            if order.side == OrderSide.SELL and execution_price < order.price:
                return ExecutionResult(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    quantity=0,
                    price=0.0,
                    timestamp=self.current_timestamp,
                    status="pending",
                    message=f"Limit sell price {order.price} above execution price {execution_price}"
                )
        
        commission = execution_price * order.quantity * self.commission_rate
        
        if order.side == OrderSide.BUY:
            cost = execution_price * order.quantity + commission
            
            if cost > self.current_capital:
                max_quantity = int((self.current_capital - commission) / execution_price)
                
                if max_quantity <= 0:
                    return ExecutionResult(
                        order_id=order.order_id,
                        symbol=order.symbol,
                        quantity=0,
                        price=0.0,
                        timestamp=self.current_timestamp,
                        status="failed",
                        message=f"Insufficient capital for order"
                    )
                
                order.quantity = max_quantity
                cost = execution_price * order.quantity + commission
            
            self.current_capital -= cost
        else:
            if order.symbol in self.positions:
                position = self.positions[order.symbol]
                
                if position.quantity < order.quantity:
                    order.quantity = position.quantity
            
            proceeds = execution_price * order.quantity - commission
            self.current_capital += proceeds
        
        if order.symbol not in self.positions:
            self.positions[order.symbol] = Position(order.symbol, 0, 0.0)
        
        position = self.positions[order.symbol]
        
        if order.side == OrderSide.BUY:
            new_quantity = position.quantity + order.quantity
            new_cost = (position.quantity * position.avg_price + order.quantity * execution_price)
            
            if new_quantity > 0:
                new_avg_price = new_cost / new_quantity
            else:
                new_avg_price = 0.0
            
            self.positions[order.symbol] = Position(
                symbol=order.symbol,
                quantity=new_quantity,
                avg_price=new_avg_price
            )
        else:
            new_quantity = position.quantity - order.quantity
            
            if new_quantity <= 0:
                self.positions[order.symbol] = Position(
                    symbol=order.symbol,
                    quantity=0,
                    avg_price=0.0
                )
            else:
                self.positions[order.symbol] = Position(
                    symbol=order.symbol,
                    quantity=new_quantity,
                    avg_price=position.avg_price
                )
        
        result = ExecutionResult(
            order_id=order.order_id,
            symbol=order.symbol,
            quantity=order.quantity,
            price=execution_price,
            timestamp=self.current_timestamp,
            status="filled",
            message=f"Order executed at {execution_price}",
            commission=commission,
            slippage=slippage,
            market_impact=market_impact
        )
        
        self.executed_orders.append(result)
        
        return result
    
    def _update_performance_metrics(self):
        """Update performance metrics."""
        portfolio_value = self.current_capital
        
        for symbol, position in self.positions.items():
            if position.quantity > 0 and symbol in self.current_prices:
                portfolio_value += position.quantity * self.current_prices[symbol]["close"]
        
        self.performance_metrics["portfolio_value"].append((self.current_timestamp, portfolio_value))
        
        if len(self.performance_metrics["portfolio_value"]) > 1:
            prev_value = self.performance_metrics["portfolio_value"][-2][1]
            current_value = portfolio_value
            
            if prev_value > 0:
                daily_return = (current_value - prev_value) / prev_value
                self.performance_metrics["returns"].append((self.current_timestamp, daily_return))
        
        if self.performance_metrics["portfolio_value"]:
            peak = max([v for _, v in self.performance_metrics["portfolio_value"]])
            drawdown = (peak - portfolio_value) / peak if peak > 0 else 0
            self.performance_metrics["drawdowns"].append((self.current_timestamp, drawdown))
            
            if self.performance_metrics["max_drawdown"] is None or drawdown > self.performance_metrics["max_drawdown"]:
                self.performance_metrics["max_drawdown"] = drawdown
        
        if self.performance_metrics["portfolio_value"]:
            initial_value = self.initial_capital
            final_value = portfolio_value
            
            self.performance_metrics["total_return"] = (final_value - initial_value) / initial_value
        
        if self.executed_orders:
            profitable_trades = 0
            total_trades = 0
            
            for result in self.executed_orders:
                if result.status == "filled":
                    total_trades += 1
                    
                    if result.side == OrderSide.BUY:
                        pass
                    else:
                        position = self.positions.get(result.symbol)
                        
                        if position and position.avg_price > 0:
                            if result.price > position.avg_price:
                                profitable_trades += 1
            
            if total_trades > 0:
                self.performance_metrics["win_rate"] = profitable_trades / total_trades
        
        if len(self.performance_metrics["returns"]) > 30:
            returns = [r for _, r in self.performance_metrics["returns"]]
            avg_return = np.mean(returns)
            std_return = np.std(returns)
            
            if std_return > 0:
                self.performance_metrics["sharpe_ratio"] = avg_return / std_return * np.sqrt(252)  # Annualized
    
    def place_order(self, order: Order) -> str:
        """
        Place an order.
        
        Args:
            order: Order to place
            
        Returns:
            Order ID
        """
        self.orders.append(order)
        return order.order_id
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID
            
        Returns:
            True if canceled, False otherwise
        """
        for i, order in enumerate(self.orders):
            if order.order_id == order_id:
                self.orders.pop(i)
                return True
        
        return False
    
    def step(self) -> Dict[str, Any]:
        """
        Advance the simulation by one step.
        
        Returns:
            Dictionary with current state
        """
        self.initialize()
        
        timestamps = self.data.index
        current_idx = list(timestamps).index(self.current_timestamp) if self.current_timestamp in timestamps else 0
        
        if current_idx + 1 >= len(timestamps):
            logger.info("Simulation complete")
            return self._get_state()
        
        self.current_timestamp = timestamps[current_idx + 1]
        
        self._update_market_condition()
        
        self._update_current_prices()
        
        self._apply_market_events()
        
        for order in list(self.orders):
            result = self._execute_order(order)
            
            if result.status in ["filled", "failed"]:
                self.orders.remove(order)
        
        self._update_performance_metrics()
        
        return self._get_state()
    
    def run(self) -> Dict[str, Any]:
        """
        Run the simulation from start to end.
        
        Returns:
            Dictionary with simulation results
        """
        self.initialize()
        
        logger.info(f"Running simulation from {self.start_date} to {self.end_date}")
        
        timestamps = self.data.index
        
        for timestamp in timestamps:
            if timestamp < self.start_date or timestamp > self.end_date:
                continue
            
            self.current_timestamp = timestamp
            
            self._update_market_condition()
            
            self._update_current_prices()
            
            self._apply_market_events()
            
            for order in list(self.orders):
                result = self._execute_order(order)
                
                if result.status in ["filled", "failed"]:
                    self.orders.remove(order)
            
            self._update_performance_metrics()
        
        logger.info("Simulation complete")
        
        return self._get_final_results()
    
    def _get_state(self) -> Dict[str, Any]:
        """
        Get the current state of the simulation.
        
        Returns:
            Dictionary with current state
        """
        return {
            "timestamp": self.current_timestamp,
            "prices": self.current_prices,
            "volumes": self.current_volumes,
            "capital": self.current_capital,
            "positions": {symbol: position.__dict__ for symbol, position in self.positions.items()},
            "market_condition": self.market_condition,
            "active_events": [event.__dict__ for event in self.market_events if event.is_applicable(self.current_timestamp, self.symbols[0])],
            "portfolio_value": self.performance_metrics["portfolio_value"][-1][1] if self.performance_metrics["portfolio_value"] else self.current_capital
        }
    
    def _get_final_results(self) -> Dict[str, Any]:
        """
        Get the final results of the simulation.
        
        Returns:
            Dictionary with simulation results
        """
        return {
            "initial_capital": self.initial_capital,
            "final_capital": self.current_capital,
            "portfolio_value": self.performance_metrics["portfolio_value"][-1][1] if self.performance_metrics["portfolio_value"] else self.current_capital,
            "total_return": self.performance_metrics["total_return"],
            "sharpe_ratio": self.performance_metrics["sharpe_ratio"],
            "max_drawdown": self.performance_metrics["max_drawdown"],
            "win_rate": self.performance_metrics["win_rate"],
            "executed_orders": len(self.executed_orders),
            "portfolio_history": self.performance_metrics["portfolio_value"],
            "returns_history": self.performance_metrics["returns"],
            "drawdown_history": self.performance_metrics["drawdowns"]
        }
    
    def reset(self):
        """Reset the simulation."""
        self.current_timestamp = self.start_date
        self.current_prices = {}
        self.current_volumes = {}
        self.current_capital = self.initial_capital
        self.positions = {}
        self.orders = []
        self.executed_orders = []
        self.market_condition = MarketCondition.NORMAL
        
        self.performance_metrics = {
            "portfolio_value": [],
            "returns": [],
            "drawdowns": [],
            "sharpe_ratio": None,
            "max_drawdown": None,
            "total_return": None,
            "win_rate": None
        }
        
        for symbol in self.symbols:
            self.positions[symbol] = Position(symbol, 0, 0.0)
        
        for event in self.market_events:
            event.is_active = False
        
        logger.info("Simulation reset")
    
    def save_results(self, path: str) -> str:
        """
        Save simulation results to a file.
        
        Args:
            path: Path to save the results
            
        Returns:
            Full path to the saved results
        """
        results = self._get_final_results()
        
        for key in ["portfolio_history", "returns_history", "drawdown_history"]:
            if key in results:
                results[key] = [(ts.isoformat(), val) for ts, val in results[key]]
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, 'w') as f:
            json.dump(results, f, indent=4)
        
        logger.info(f"Simulation results saved to {path}")
        
        return path
    
    def load_data(self, path: str) -> pd.DataFrame:
        """
        Load market data from a file.
        
        Args:
            path: Path to the data file
            
        Returns:
            DataFrame with market data
        """
        if path.endswith('.csv'):
            data = pd.read_csv(path, index_col=0, parse_dates=True)
        elif path.endswith('.parquet'):
            data = pd.read_parquet(path)
        else:
            raise ValueError(f"Unsupported file format: {path}")
        
        self.data = data
        
        logger.info(f"Loaded market data from {path} with {len(data)} rows")
        
        return data
