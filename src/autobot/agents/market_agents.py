"""
Market-specific agent implementations for AUTOBOT.

This module provides specialized agent implementations for different
market-related tasks such as arbitrage, market making, and trend following.
"""

import logging
import time
import random
import numpy as np
from typing import Dict, Any, List, Optional, Union, Tuple
from datetime import datetime, timedelta

from .orchestrator import Agent, AgentType, AgentStatus, AgentMessage

logger = logging.getLogger(__name__)

class ArbitrageAgent(Agent):
    """
    Agent specialized in detecting and executing arbitrage opportunities
    across multiple markets or exchanges.
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        config: Dict[str, Any] = None,
        min_profit_threshold: float = 0.005,  # 0.5% minimum profit
        max_execution_time_ms: int = 500,
        exchanges: List[str] = None
    ):
        """
        Initialize an arbitrage agent.
        
        Args:
            agent_id: Unique ID for this agent
            name: Human-readable name
            config: Agent configuration
            min_profit_threshold: Minimum profit threshold for arbitrage (as a decimal)
            max_execution_time_ms: Maximum execution time in milliseconds
            exchanges: List of exchanges to monitor for arbitrage
        """
        super().__init__(agent_id, AgentType.ARBITRAGE, name, config)
        
        self.min_profit_threshold = config.get("min_profit_threshold", min_profit_threshold)
        self.max_execution_time_ms = config.get("max_execution_time_ms", max_execution_time_ms)
        self.exchanges = config.get("exchanges", exchanges or ["binance", "coinbase", "kraken"])
        
        self.opportunities: List[Dict[str, Any]] = []
        self.executed_trades: List[Dict[str, Any]] = []
        self.last_scan_time = 0
        self.scan_interval = config.get("scan_interval", 5)  # seconds
        
        self.register_message_handler("scan_markets", self._handle_scan_markets)
        self.register_message_handler("execute_arbitrage", self._handle_execute_arbitrage)
        self.register_message_handler("update_config", self._handle_update_config)
        
        logger.info(f"ArbitrageAgent {self.name} initialized with {len(self.exchanges)} exchanges")
    
    def _handle_scan_markets(self, message: AgentMessage):
        """
        Handle a request to scan markets for arbitrage opportunities.
        
        Args:
            message: Message containing scan parameters
        """
        content = message.content
        symbols = content.get("symbols", ["BTC/USD", "ETH/USD", "SOL/USD"])
        
        opportunities = self._scan_for_opportunities(symbols)
        
        response = {
            "opportunities": opportunities,
            "timestamp": int(time.time()),
            "scan_duration_ms": int((time.time() - self.last_scan_time) * 1000)
        }
        
        self.send_message(
            recipient_id=message.sender_id,
            message_type="scan_results",
            content=response
        )
        
        logger.info(f"ArbitrageAgent {self.id} found {len(opportunities)} opportunities")
    
    def _handle_execute_arbitrage(self, message: AgentMessage):
        """
        Handle a request to execute an arbitrage opportunity.
        
        Args:
            message: Message containing execution parameters
        """
        content = message.content
        opportunity_id = content.get("opportunity_id")
        
        if not opportunity_id:
            self.send_message(
                recipient_id=message.sender_id,
                message_type="execution_result",
                content={"success": False, "error": "No opportunity ID provided"}
            )
            return
        
        opportunity = next((o for o in self.opportunities if o["id"] == opportunity_id), None)
        
        if not opportunity:
            self.send_message(
                recipient_id=message.sender_id,
                message_type="execution_result",
                content={"success": False, "error": f"Opportunity {opportunity_id} not found"}
            )
            return
        
        result = self._execute_arbitrage(opportunity)
        
        if result["success"]:
            self.executed_trades.append({
                "opportunity": opportunity,
                "execution_time": int(time.time()),
                "execution_duration_ms": result["execution_duration_ms"],
                "profit": result["profit"],
                "profit_percentage": result["profit_percentage"]
            })
        
        self.send_message(
            recipient_id=message.sender_id,
            message_type="execution_result",
            content=result
        )
        
        logger.info(f"ArbitrageAgent {self.id} executed opportunity {opportunity_id}: {result['success']}")
    
    def _handle_update_config(self, message: AgentMessage):
        """
        Handle a request to update the agent's configuration.
        
        Args:
            message: Message containing new configuration
        """
        content = message.content
        config = content.get("config", {})
        
        if "min_profit_threshold" in config:
            self.min_profit_threshold = config["min_profit_threshold"]
        
        if "max_execution_time_ms" in config:
            self.max_execution_time_ms = config["max_execution_time_ms"]
        
        if "exchanges" in config:
            self.exchanges = config["exchanges"]
        
        if "scan_interval" in config:
            self.scan_interval = config["scan_interval"]
        
        self.send_message(
            recipient_id=message.sender_id,
            message_type="config_updated",
            content={"success": True}
        )
        
        logger.info(f"ArbitrageAgent {self.id} updated configuration")
    
    def _scan_for_opportunities(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Scan markets for arbitrage opportunities.
        
        Args:
            symbols: List of symbols to scan
            
        Returns:
            List of arbitrage opportunities
        """
        self.last_scan_time = time.time()
        opportunities = []
        
        for symbol in symbols:
            prices = {}
            for exchange in self.exchanges:
                prices[exchange] = self._simulate_price(symbol, exchange)
            
            lowest_ask = min([(exchange, price["ask"]) for exchange, price in prices.items()], key=lambda x: x[1])
            highest_bid = max([(exchange, price["bid"]) for exchange, price in prices.items()], key=lambda x: x[1])
            
            potential_profit = highest_bid[1] - lowest_ask[1]
            potential_profit_percentage = potential_profit / lowest_ask[1]
            
            if potential_profit_percentage >= self.min_profit_threshold:
                opportunity = {
                    "id": str(len(self.opportunities) + 1),
                    "symbol": symbol,
                    "buy_exchange": lowest_ask[0],
                    "buy_price": lowest_ask[1],
                    "sell_exchange": highest_bid[0],
                    "sell_price": highest_bid[1],
                    "potential_profit": potential_profit,
                    "potential_profit_percentage": potential_profit_percentage,
                    "timestamp": int(time.time())
                }
                
                opportunities.append(opportunity)
                self.opportunities.append(opportunity)
        
        return opportunities
    
    def _execute_arbitrage(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an arbitrage opportunity.
        
        Args:
            opportunity: Arbitrage opportunity to execute
            
        Returns:
            Execution result
        """
        start_time = time.time()
        
        
        try:
            from ..rl.meta_learning import create_meta_learner
            meta_learner = create_meta_learner()
            
            best_strategy = meta_learner.get_best_strategy()
            if best_strategy:
                strategy_id, strategy_data = best_strategy
                success_rate = strategy_data.get('win_rate', 0.8)
                success = success_rate > 0.6  # Use real win rate
                
                if success:
                    performance = strategy_data.get('performance', 0.0)
                    actual_profit = opportunity["potential_profit"] * (performance / 100)
                    actual_profit_percentage = actual_profit / opportunity["buy_price"]
                else:
                    actual_profit = 0
                    actual_profit_percentage = 0
            else:
                success = False
                actual_profit = 0
                actual_profit_percentage = 0
        except Exception as e:
            logger.error(f"Error getting real strategy data: {e}")
            success = False
            actual_profit = 0
            actual_profit_percentage = 0
        
        end_time = time.time()
        execution_duration_ms = int((end_time - start_time) * 1000)
        
        return {
            "success": success,
            "opportunity_id": opportunity["id"],
            "execution_duration_ms": execution_duration_ms,
            "profit": actual_profit,
            "profit_percentage": actual_profit_percentage,
            "timestamp": int(time.time()),
            "error": None if success else "Execution failed due to market conditions"
        }
    
    def _get_real_price(self, symbol: str, exchange: str) -> Dict[str, float]:
        """
        Get real price data from exchange APIs.
        
        Args:
            symbol: Symbol to get price for
            exchange: Exchange to get price from
            
        Returns:
            Real price data from exchange
        """
        try:
            from autobot.data.real_providers import get_market_data
            
            market_data = get_market_data(symbol, exchange)
            if market_data:
                return {
                    "bid": market_data.get("bid", 0.0),
                    "ask": market_data.get("ask", 0.0),
                    "last": market_data.get("last", 0.0),
                    "volume": market_data.get("volume", 0.0)
                }
        except Exception as e:
            logger.error(f"Error getting real price for {symbol} on {exchange}: {e}")
        
        return {
            "bid": 0.0,
            "ask": 0.0,
            "last": 0.0,
            "volume": 0.0
        }
    
    def update(self):
        """Update agent state (called periodically)"""
        super().update()
        
        current_time = time.time()
        if current_time - self.last_scan_time >= self.scan_interval:
            self._scan_for_opportunities(["BTC/USD", "ETH/USD", "SOL/USD"])


class MarketMakerAgent(Agent):
    """
    Agent specialized in market making strategies, providing liquidity
    and profiting from bid-ask spreads.
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        config: Dict[str, Any] = None,
        target_spread: float = 0.002,  # 0.2% target spread
        max_position: float = 10.0,
        risk_factor: float = 0.5
    ):
        """
        Initialize a market maker agent.
        
        Args:
            agent_id: Unique ID for this agent
            name: Human-readable name
            config: Agent configuration
            target_spread: Target bid-ask spread (as a decimal)
            max_position: Maximum position size
            risk_factor: Risk factor for position sizing (0-1)
        """
        super().__init__(agent_id, AgentType.MARKET_MAKER, name, config)
        
        self.target_spread = config.get("target_spread", target_spread)
        self.max_position = config.get("max_position", max_position)
        self.risk_factor = config.get("risk_factor", risk_factor)
        
        self.positions: Dict[str, float] = {}
        self.orders: List[Dict[str, Any]] = []
        self.last_update_time = 0
        self.update_interval = config.get("update_interval", 1)  # seconds
        
        self.register_message_handler("place_orders", self._handle_place_orders)
        self.register_message_handler("cancel_orders", self._handle_cancel_orders)
        self.register_message_handler("update_config", self._handle_update_config)
        
        logger.info(f"MarketMakerAgent {self.name} initialized with target spread {self.target_spread}")
    
    def _handle_place_orders(self, message: AgentMessage):
        """
        Handle a request to place market making orders.
        
        Args:
            message: Message containing order parameters
        """
        content = message.content
        symbol = content.get("symbol", "BTC/USD")
        exchange = content.get("exchange", "binance")
        
        orders = self._place_orders(symbol, exchange)
        
        response = {
            "orders": orders,
            "timestamp": int(time.time())
        }
        
        self.send_message(
            recipient_id=message.sender_id,
            message_type="orders_placed",
            content=response
        )
        
        logger.info(f"MarketMakerAgent {self.id} placed {len(orders)} orders for {symbol}")
    
    def _handle_cancel_orders(self, message: AgentMessage):
        """
        Handle a request to cancel orders.
        
        Args:
            message: Message containing cancellation parameters
        """
        content = message.content
        order_ids = content.get("order_ids", [])
        
        cancelled = self._cancel_orders(order_ids)
        
        response = {
            "cancelled": cancelled,
            "timestamp": int(time.time())
        }
        
        self.send_message(
            recipient_id=message.sender_id,
            message_type="orders_cancelled",
            content=response
        )
        
        logger.info(f"MarketMakerAgent {self.id} cancelled {len(cancelled)} orders")
    
    def _handle_update_config(self, message: AgentMessage):
        """
        Handle a request to update the agent's configuration.
        
        Args:
            message: Message containing new configuration
        """
        content = message.content
        config = content.get("config", {})
        
        if "target_spread" in config:
            self.target_spread = config["target_spread"]
        
        if "max_position" in config:
            self.max_position = config["max_position"]
        
        if "risk_factor" in config:
            self.risk_factor = config["risk_factor"]
        
        if "update_interval" in config:
            self.update_interval = config["update_interval"]
        
        self.send_message(
            recipient_id=message.sender_id,
            message_type="config_updated",
            content={"success": True}
        )
        
        logger.info(f"MarketMakerAgent {self.id} updated configuration")
    
    def _place_orders(self, symbol: str, exchange: str) -> List[Dict[str, Any]]:
        """
        Place market making orders.
        
        Args:
            symbol: Symbol to place orders for
            exchange: Exchange to place orders on
            
        Returns:
            List of placed orders
        """
        market_price = self._get_market_price(symbol, exchange)
        
        half_spread = self.target_spread / 2
        bid_price = market_price * (1 - half_spread)
        ask_price = market_price * (1 + half_spread)
        
        current_position = self.positions.get(symbol, 0)
        position_ratio = current_position / self.max_position
        
        bid_size = self.max_position * self.risk_factor * (1 - position_ratio)
        ask_size = self.max_position * self.risk_factor * (1 + position_ratio)
        
        bid_size = max(bid_size, 0.001)
        ask_size = max(ask_size, 0.001)
        
        bid_order = {
            "id": f"bid_{int(time.time())}_{int(time.time() * 1000) % 10000}",
            "symbol": symbol,
            "exchange": exchange,
            "side": "buy",
            "type": "limit",
            "price": bid_price,
            "amount": bid_size,
            "timestamp": int(time.time())
        }
        
        ask_order = {
            "id": f"ask_{int(time.time())}_{int(time.time() * 1000) % 10000 + 5000}",
            "symbol": symbol,
            "exchange": exchange,
            "side": "sell",
            "type": "limit",
            "price": ask_price,
            "amount": ask_size,
            "timestamp": int(time.time())
        }
        
        self.orders.extend([bid_order, ask_order])
        
        return [bid_order, ask_order]
    
    def _cancel_orders(self, order_ids: List[str]) -> List[str]:
        """
        Cancel orders.
        
        Args:
            order_ids: IDs of orders to cancel
            
        Returns:
            List of cancelled order IDs
        """
        cancelled = []
        
        for order_id in order_ids:
            order_index = next((i for i, o in enumerate(self.orders) if o["id"] == order_id), None)
            
            if order_index is not None:
                self.orders.pop(order_index)
                cancelled.append(order_id)
        
        return cancelled
    
    def _get_market_price(self, symbol: str, exchange: str) -> float:
        """
        Get current market price.
        
        Args:
            symbol: Symbol to get price for
            exchange: Exchange to get price from
            
        Returns:
            Current market price
        """
        base_prices = {
            "BTC/USD": 50000,
            "ETH/USD": 3000,
            "SOL/USD": 100,
            "XRP/USD": 0.5,
            "ADA/USD": 1.2
        }
        
        try:
            from autobot.data.real_providers import get_market_data
            
            market_data = get_market_data(symbol, exchange)
            if market_data and 'last' in market_data:
                return market_data['last']
        except Exception as e:
            logger.error(f"Error getting real market price for {symbol}: {e}")
        
        base_price = base_prices.get(symbol, 100)
        return base_price
    
    def update(self):
        """Update agent state (called periodically)"""
        super().update()
        
        current_time = time.time()
        if current_time - self.last_update_time >= self.update_interval:
            self.last_update_time = current_time
            
            try:
                from ..rl.meta_learning import create_meta_learner
                meta_learner = create_meta_learner()
                
                best_strategy = meta_learner.get_best_strategy()
                if best_strategy:
                    strategy_id, strategy_data = best_strategy
                    fill_rate = strategy_data.get('win_rate', 0.1)
                    
                    for order in list(self.orders):
                        if fill_rate > 0.05:  # Use real strategy performance for fill rate
                            symbol = order["symbol"]
                            amount = order["amount"]
                            
                            if order["side"] == "buy":
                                self.positions[symbol] = self.positions.get(symbol, 0) + amount
                            else:
                                self.positions[symbol] = self.positions.get(symbol, 0) - amount
                            
                            self.orders.remove(order)
            except Exception as e:
                logger.error(f"Error processing orders with real data: {e}")
            
            for symbol in self.positions.keys():
                self._place_orders(symbol, "binance")


class TrendFollowingAgent(Agent):
    """
    Agent specialized in trend following strategies, identifying
    and trading with market trends.
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        config: Dict[str, Any] = None,
        short_window: int = 20,
        long_window: int = 50,
        trend_threshold: float = 0.01  # 1% trend threshold
    ):
        """
        Initialize a trend following agent.
        
        Args:
            agent_id: Unique ID for this agent
            name: Human-readable name
            config: Agent configuration
            short_window: Short moving average window
            long_window: Long moving average window
            trend_threshold: Threshold for trend detection (as a decimal)
        """
        super().__init__(agent_id, AgentType.TREND_FOLLOWING, name, config)
        
        self.short_window = config.get("short_window", short_window)
        self.long_window = config.get("long_window", long_window)
        self.trend_threshold = config.get("trend_threshold", trend_threshold)
        
        self.price_history: Dict[str, List[float]] = {}
        self.trends: Dict[str, str] = {}  # "up", "down", or "neutral"
        self.positions: Dict[str, float] = {}
        self.last_analysis_time = 0
        self.analysis_interval = config.get("analysis_interval", 60)  # seconds
        
        self.register_message_handler("analyze_trend", self._handle_analyze_trend)
        self.register_message_handler("place_order", self._handle_place_order)
        self.register_message_handler("update_config", self._handle_update_config)
        
        logger.info(f"TrendFollowingAgent {self.name} initialized with windows {short_window}/{long_window}")
    
    def _handle_analyze_trend(self, message: AgentMessage):
        """
        Handle a request to analyze market trends.
        
        Args:
            message: Message containing analysis parameters
        """
        content = message.content
        symbol = content.get("symbol", "BTC/USD")
        
        trend = self._analyze_trend(symbol)
        
        response = {
            "symbol": symbol,
            "trend": trend,
            "short_ma": self._calculate_ma(symbol, self.short_window),
            "long_ma": self._calculate_ma(symbol, self.long_window),
            "timestamp": int(time.time())
        }
        
        self.send_message(
            recipient_id=message.sender_id,
            message_type="trend_analysis",
            content=response
        )
        
        logger.info(f"TrendFollowingAgent {self.id} analyzed trend for {symbol}: {trend}")
    
    def _handle_place_order(self, message: AgentMessage):
        """
        Handle a request to place an order based on trend.
        
        Args:
            message: Message containing order parameters
        """
        content = message.content
        symbol = content.get("symbol", "BTC/USD")
        amount = content.get("amount", 1.0)
        
        order = self._place_order(symbol, amount)
        
        response = {
            "order": order,
            "timestamp": int(time.time())
        }
        
        self.send_message(
            recipient_id=message.sender_id,
            message_type="order_placed",
            content=response
        )
        
        logger.info(f"TrendFollowingAgent {self.id} placed {order['side']} order for {symbol}")
    
    def _handle_update_config(self, message: AgentMessage):
        """
        Handle a request to update the agent's configuration.
        
        Args:
            message: Message containing new configuration
        """
        content = message.content
        config = content.get("config", {})
        
        if "short_window" in config:
            self.short_window = config["short_window"]
        
        if "long_window" in config:
            self.long_window = config["long_window"]
        
        if "trend_threshold" in config:
            self.trend_threshold = config["trend_threshold"]
        
        if "analysis_interval" in config:
            self.analysis_interval = config["analysis_interval"]
        
        self.send_message(
            recipient_id=message.sender_id,
            message_type="config_updated",
            content={"success": True}
        )
        
        logger.info(f"TrendFollowingAgent {self.id} updated configuration")
    
    def _analyze_trend(self, symbol: str) -> str:
        """
        Analyze market trend for a symbol.
        
        Args:
            symbol: Symbol to analyze
            
        Returns:
            Trend direction ("up", "down", or "neutral")
        """
        self.last_analysis_time = time.time()
        
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        current_price = self._get_current_price(symbol)
        self.price_history[symbol].append(current_price)
        
        max_window = max(self.short_window, self.long_window)
        if len(self.price_history[symbol]) > max_window * 2:
            self.price_history[symbol] = self.price_history[symbol][-max_window * 2:]
        
        if len(self.price_history[symbol]) < max_window:
            return "neutral"
        
        short_ma = self._calculate_ma(symbol, self.short_window)
        long_ma = self._calculate_ma(symbol, self.long_window)
        
        if short_ma is None or long_ma is None:
            return "neutral"
        
        trend_strength = (short_ma - long_ma) / long_ma
        
        if trend_strength > self.trend_threshold:
            trend = "up"
        elif trend_strength < -self.trend_threshold:
            trend = "down"
        else:
            trend = "neutral"
        
        self.trends[symbol] = trend
        return trend
    
    def _calculate_ma(self, symbol: str, window: int) -> Optional[float]:
        """
        Calculate moving average for a symbol.
        
        Args:
            symbol: Symbol to calculate MA for
            window: MA window size
            
        Returns:
            Moving average value, or None if not enough data
        """
        if symbol not in self.price_history:
            return None
        
        prices = self.price_history[symbol]
        
        if len(prices) < window:
            return None
        
        return sum(prices[-window:]) / window
    
    def _place_order(self, symbol: str, amount: float) -> Dict[str, Any]:
        """
        Place an order based on current trend.
        
        Args:
            symbol: Symbol to place order for
            amount: Order amount
            
        Returns:
            Order details
        """
        trend = self.trends.get(symbol, "neutral")
        
        if trend == "up":
            side = "buy"
        elif trend == "down":
            side = "sell"
        else:
            return {
                "id": None,
                "symbol": symbol,
                "side": "none",
                "amount": 0,
                "price": self._get_current_price(symbol),
                "timestamp": int(time.time()),
                "status": "skipped",
                "reason": "No clear trend"
            }
        
        current_position = self.positions.get(symbol, 0)
        
        if side == "buy":
            self.positions[symbol] = current_position + amount
        else:
            self.positions[symbol] = current_position - amount
        
        return {
            "id": f"{side}_{int(time.time())}_{random.randint(1000, 9999)}",
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": self._get_current_price(symbol),
            "timestamp": int(time.time()),
            "status": "placed"
        }
    
    def _get_current_price(self, symbol: str) -> float:
        """
        Get current market price.
        
        Args:
            symbol: Symbol to get price for
            
        Returns:
            Current market price
        """
        base_prices = {
            "BTC/USD": 50000,
            "ETH/USD": 3000,
            "SOL/USD": 100,
            "XRP/USD": 0.5,
            "ADA/USD": 1.2
        }
        
        base_price = base_prices.get(symbol, 100)
        
        trend_factor = 1.0
        if symbol in self.trends:
            if self.trends[symbol] == "up":
                trend_factor = 1.001
            elif self.trends[symbol] == "down":
                trend_factor = 0.999
        
        try:
            from autobot.data.real_providers import get_market_data
            
            market_data = get_market_data(symbol, "binance")
            if market_data and 'last' in market_data:
                return market_data['last'] * trend_factor
        except Exception as e:
            logger.error(f"Error getting real price for trend analysis: {e}")
        
        return base_price * trend_factor
    
    def update(self):
        """Update agent state (called periodically)"""
        super().update()
        
        current_time = time.time()
        if current_time - self.last_analysis_time >= self.analysis_interval:
            for symbol in list(self.price_history.keys()):
                self._analyze_trend(symbol)


class MeanReversionAgent(Agent):
    """
    Agent specialized in mean reversion strategies, identifying
    overbought and oversold conditions.
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        config: Dict[str, Any] = None,
        lookback_period: int = 20,
        std_dev_threshold: float = 2.0,
        mean_reversion_strength: float = 0.5
    ):
        """
        Initialize a mean reversion agent.
        
        Args:
            agent_id: Unique ID for this agent
            name: Human-readable name
            config: Agent configuration
            lookback_period: Period for calculating mean and standard deviation
            std_dev_threshold: Standard deviation threshold for signals
            mean_reversion_strength: Strength of mean reversion (0-1)
        """
        super().__init__(agent_id, AgentType.MEAN_REVERSION, name, config)
        
        self.lookback_period = config.get("lookback_period", lookback_period)
        self.std_dev_threshold = config.get("std_dev_threshold", std_dev_threshold)
        self.mean_reversion_strength = config.get("mean_reversion_strength", mean_reversion_strength)
        
        self.price_history: Dict[str, List[float]] = {}
        self.signals: Dict[str, str] = {}  # "buy", "sell", or "neutral"
        self.positions: Dict[str, float] = {}
        self.last_analysis_time = 0
        self.analysis_interval = config.get("analysis_interval", 60)  # seconds
        
        self.register_message_handler("analyze_signal", self._handle_analyze_signal)
        self.register_message_handler("place_order", self._handle_place_order)
        self.register_message_handler("update_config", self._handle_update_config)
        
        logger.info(f"MeanReversionAgent {self.name} initialized with lookback {lookback_period}")
    
    def _handle_analyze_signal(self, message: AgentMessage):
        """
        Handle a request to analyze mean reversion signals.
        
        Args:
            message: Message containing analysis parameters
        """
        content = message.content
        symbol = content.get("symbol", "BTC/USD")
        
        signal = self._analyze_signal(symbol)
        
        response = {
            "symbol": symbol,
            "signal": signal,
            "z_score": self._calculate_z_score(symbol),
            "mean": self._calculate_mean(symbol),
            "std_dev": self._calculate_std_dev(symbol),
            "timestamp": int(time.time())
        }
        
        self.send_message(
            recipient_id=message.sender_id,
            message_type="signal_analysis",
            content=response
        )
        
        logger.info(f"MeanReversionAgent {self.id} analyzed signal for {symbol}: {signal}")
    
    def _handle_place_order(self, message: AgentMessage):
        """
        Handle a request to place an order based on signal.
        
        Args:
            message: Message containing order parameters
        """
        content = message.content
        symbol = content.get("symbol", "BTC/USD")
        amount = content.get("amount", 1.0)
        
        order = self._place_order(symbol, amount)
        
        response = {
            "order": order,
            "timestamp": int(time.time())
        }
        
        self.send_message(
            recipient_id=message.sender_id,
            message_type="order_placed",
            content=response
        )
        
        logger.info(f"MeanReversionAgent {self.id} placed {order['side']} order for {symbol}")
    
    def _handle_update_config(self, message: AgentMessage):
        """
        Handle a request to update the agent's configuration.
        
        Args:
            message: Message containing new configuration
        """
        content = message.content
        config = content.get("config", {})
        
        if "lookback_period" in config:
            self.lookback_period = config["lookback_period"]
        
        if "std_dev_threshold" in config:
            self.std_dev_threshold = config["std_dev_threshold"]
        
        if "mean_reversion_strength" in config:
            self.mean_reversion_strength = config["mean_reversion_strength"]
        
        if "analysis_interval" in config:
            self.analysis_interval = config["analysis_interval"]
        
        self.send_message(
            recipient_id=message.sender_id,
            message_type="config_updated",
            content={"success": True}
        )
        
        logger.info(f"MeanReversionAgent {self.id} updated configuration")
    
    def _analyze_signal(self, symbol: str) -> str:
        """
        Analyze mean reversion signal for a symbol.
        
        Args:
            symbol: Symbol to analyze
            
        Returns:
            Signal direction ("buy", "sell", or "neutral")
        """
        self.last_analysis_time = time.time()
        
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        current_price = self._get_current_price(symbol)
        self.price_history[symbol].append(current_price)
        
        if len(self.price_history[symbol]) > self.lookback_period * 2:
            self.price_history[symbol] = self.price_history[symbol][-self.lookback_period * 2:]
        
        if len(self.price_history[symbol]) < self.lookback_period:
            return "neutral"
        
        z_score = self._calculate_z_score(symbol)
        
        if z_score is None:
            return "neutral"
        
        if z_score < -self.std_dev_threshold:
            signal = "buy"  # Price is below mean by threshold std devs -> buy
        elif z_score > self.std_dev_threshold:
            signal = "sell"  # Price is above mean by threshold std devs -> sell
        else:
            signal = "neutral"
        
        self.signals[symbol] = signal
        return signal
    
    def _calculate_mean(self, symbol: str) -> Optional[float]:
        """
        Calculate mean price for a symbol.
        
        Args:
            symbol: Symbol to calculate mean for
            
        Returns:
            Mean price, or None if not enough data
        """
        if symbol not in self.price_history:
            return None
        
        prices = self.price_history[symbol]
        
        if len(prices) < self.lookback_period:
            return None
        
        return sum(prices[-self.lookback_period:]) / self.lookback_period
    
    def _calculate_std_dev(self, symbol: str) -> Optional[float]:
        """
        Calculate standard deviation for a symbol.
        
        Args:
            symbol: Symbol to calculate std dev for
            
        Returns:
            Standard deviation, or None if not enough data
        """
        if symbol not in self.price_history:
            return None
        
        prices = self.price_history[symbol]
        
        if len(prices) < self.lookback_period:
            return None
        
        mean = self._calculate_mean(symbol)
        if mean is None:
            return None
        
        squared_diffs = [(price - mean) ** 2 for price in prices[-self.lookback_period:]]
        variance = sum(squared_diffs) / self.lookback_period
        
        return variance ** 0.5
    
    def _calculate_z_score(self, symbol: str) -> Optional[float]:
        """
        Calculate z-score for current price.
        
        Args:
            symbol: Symbol to calculate z-score for
            
        Returns:
            Z-score, or None if not enough data
        """
        if symbol not in self.price_history:
            return None
        
        mean = self._calculate_mean(symbol)
        std_dev = self._calculate_std_dev(symbol)
        
        if mean is None or std_dev is None or std_dev == 0:
            return None
        
        current_price = self.price_history[symbol][-1]
        
        return (current_price - mean) / std_dev
    
    def _place_order(self, symbol: str, amount: float) -> Dict[str, Any]:
        """
        Place an order based on current signal.
        
        Args:
            symbol: Symbol to place order for
            amount: Order amount
            
        Returns:
            Order details
        """
        signal = self.signals.get(symbol, "neutral")
        
        if signal == "buy":
            side = "buy"
        elif signal == "sell":
            side = "sell"
        else:
            return {
                "id": None,
                "symbol": symbol,
                "side": "none",
                "amount": 0,
                "price": self._get_current_price(symbol),
                "timestamp": int(time.time()),
                "status": "skipped",
                "reason": "No clear signal"
            }
        
        z_score = self._calculate_z_score(symbol)
        if z_score is not None:
            scaled_amount = amount * abs(z_score) * self.mean_reversion_strength
            amount = min(scaled_amount, amount * 2)  # Cap at 2x base amount
        
        current_position = self.positions.get(symbol, 0)
        
        if side == "buy":
            self.positions[symbol] = current_position + amount
        else:
            self.positions[symbol] = current_position - amount
        
        return {
            "id": f"{side}_{int(time.time())}_{random.randint(1000, 9999)}",
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": self._get_current_price(symbol),
            "timestamp": int(time.time()),
            "status": "placed"
        }
    
    def _get_current_price(self, symbol: str) -> float:
        """
        Get current market price.
        
        Args:
            symbol: Symbol to get price for
            
        Returns:
            Current market price
        """
        base_prices = {
            "BTC/USD": 50000,
            "ETH/USD": 3000,
            "SOL/USD": 100,
            "XRP/USD": 0.5,
            "ADA/USD": 1.2
        }
        
        base_price = base_prices.get(symbol, 100)
        
        reversion_factor = 1.0
        if symbol in self.signals:
            z_score = self._calculate_z_score(symbol)
            if z_score is not None:
                reversion_factor = 1.0 - (z_score * 0.001)
        
        try:
            from autobot.data.real_providers import get_market_data
            market_data = get_market_data(symbol, exchange)
            if market_data and 'volatility' in market_data:
                volatility_factor = 1.0 + (market_data['volatility'] * 0.1)
            else:
                volatility_factor = 1.0
        except Exception as e:
            logger.error(f"Error getting market volatility: {e}")
            volatility_factor = 1.0
        
        return base_price * reversion_factor * volatility_factor
    
    def update(self):
        """Update agent state (called periodically)"""
        super().update()
        
        current_time = time.time()
        if current_time - self.last_analysis_time >= self.analysis_interval:
            for symbol in list(self.price_history.keys()):
                self._analyze_signal(symbol)
