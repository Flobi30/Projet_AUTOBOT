"""
Binance Connector for AUTOBOT Grid Trading Engine.

Provides connectivity to Binance Spot exchange for:
- Real-time price data via WebSocket
- Order placement and management
- Account balance queries
- Paper trading simulation
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import json

logger = logging.getLogger(__name__)


@dataclass
class BinanceConfig:
    """
    Configuration for Binance connector.
    
    Attributes:
        api_key: Binance API key
        api_secret: Binance API secret
        testnet: Use testnet instead of production
        recv_window: Request receive window in ms
        rate_limit: Max requests per second
    """
    api_key: str = ""
    api_secret: str = ""
    testnet: bool = True
    recv_window: int = 5000
    rate_limit: int = 10
    
    @classmethod
    def from_env(cls) -> "BinanceConfig":
        """Create config from environment variables."""
        return cls(
            api_key=os.getenv("BINANCE_API_KEY", ""),
            api_secret=os.getenv("BINANCE_API_SECRET", ""),
            testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true",
        )


class BinanceConnector:
    """
    Binance exchange connector for grid trading.
    
    Supports both real trading and paper trading modes.
    Uses ccxt library for exchange operations when available.
    
    Example:
        config = BinanceConfig.from_env()
        connector = BinanceConnector(config)
        
        await connector.connect()
        
        # Get current price
        price = await connector.get_ticker("BTC/USDT")
        
        # Place order
        order = await connector.create_order(
            symbol="BTCUSDT",
            side="BUY",
            type="LIMIT",
            quantity=0.001,
            price=50000.0
        )
    """
    
    # Binance API endpoints
    SPOT_API = "https://api.binance.com"
    SPOT_TESTNET_API = "https://testnet.binance.vision"
    WS_SPOT = "wss://stream.binance.com:9443/ws"
    WS_SPOT_TESTNET = "wss://testnet.binance.vision/ws"
    
    def __init__(
        self,
        config: Optional[BinanceConfig] = None,
        paper_trading: bool = True
    ):
        """
        Initialize Binance connector.
        
        Args:
            config: Binance configuration
            paper_trading: If True, simulate orders without real execution
        """
        self.config = config or BinanceConfig()
        self.paper_trading = paper_trading
        
        self._exchange = None
        self._ws_connection = None
        self._is_connected = False
        self._last_price: Dict[str, float] = {}
        self._order_book: Dict[str, Dict] = {}
        
        self._price_callbacks: List[Callable] = []
        self._order_callbacks: List[Callable] = []
        
        self._paper_balance: Dict[str, float] = {
            "USDT": 500.0,
            "BTC": 0.0,
            "ETH": 0.0,
        }
        self._paper_orders: Dict[str, Dict] = {}
        self._paper_order_id = 1000000
        
        logger.info(
            f"BinanceConnector initialized: testnet={self.config.testnet}, "
            f"paper_trading={paper_trading}"
        )
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to exchange."""
        return self._is_connected
    
    @property
    def base_url(self) -> str:
        """Get base API URL."""
        if self.config.testnet:
            return self.SPOT_TESTNET_API
        return self.SPOT_API
    
    @property
    def ws_url(self) -> str:
        """Get WebSocket URL."""
        if self.config.testnet:
            return self.WS_SPOT_TESTNET
        return self.WS_SPOT
    
    async def connect(self) -> bool:
        """
        Connect to Binance exchange.
        
        Returns:
            True if connection successful
        """
        try:
            try:
                import ccxt.async_support as ccxt
                
                exchange_class = ccxt.binance
                
                self._exchange = exchange_class({
                    'apiKey': self.config.api_key,
                    'secret': self.config.api_secret,
                    'sandbox': self.config.testnet,
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'spot',
                        'recvWindow': self.config.recv_window,
                    }
                })
                
                await self._exchange.load_markets()
                self._is_connected = True
                logger.info("Connected to Binance via ccxt")
                
            except ImportError:
                logger.warning("ccxt not available, using paper trading only")
                self._is_connected = True
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from Binance."""
        if self._exchange:
            await self._exchange.close()
            self._exchange = None
        
        if self._ws_connection:
            await self._ws_connection.close()
            self._ws_connection = None
        
        self._is_connected = False
        logger.info("Disconnected from Binance")
    
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get current ticker data for a symbol.
        
        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            
        Returns:
            Ticker data with bid, ask, last price
        """
        if self._exchange:
            try:
                ticker = await self._exchange.fetch_ticker(symbol)
                self._last_price[symbol] = ticker['last']
                return {
                    "symbol": symbol,
                    "bid": ticker['bid'],
                    "ask": ticker['ask'],
                    "last": ticker['last'],
                    "volume": ticker['baseVolume'],
                    "timestamp": ticker['timestamp'],
                }
            except Exception as e:
                logger.error(f"Failed to get ticker: {e}")
        
        return {
            "symbol": symbol,
            "bid": self._last_price.get(symbol, 50000.0) * 0.9999,
            "ask": self._last_price.get(symbol, 50000.0) * 1.0001,
            "last": self._last_price.get(symbol, 50000.0),
            "volume": 1000.0,
            "timestamp": int(time.time() * 1000),
        }
    
    async def get_balance(self) -> Dict[str, float]:
        """
        Get account balances.
        
        Returns:
            Dictionary of currency -> balance
        """
        if self.paper_trading:
            return self._paper_balance.copy()
        
        if self._exchange:
            try:
                balance = await self._exchange.fetch_balance()
                return {
                    currency: data['free']
                    for currency, data in balance['total'].items()
                    if data['free'] > 0
                }
            except Exception as e:
                logger.error(f"Failed to get balance: {e}")
        
        return self._paper_balance.copy()
    
    async def create_order(
        self,
        symbol: str,
        side: str,
        type: str,
        quantity: float,
        price: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create an order on Binance.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: "BUY" or "SELL"
            type: "LIMIT" or "MARKET"
            quantity: Order quantity
            price: Limit price (required for LIMIT orders)
            
        Returns:
            Order response from exchange
        """
        if self.paper_trading:
            return await self._create_paper_order(symbol, side, type, quantity, price)
        
        if self._exchange:
            try:
                ccxt_symbol = symbol.replace("USDT", "/USDT").replace("BTC", "BTC")
                if "/" not in ccxt_symbol:
                    ccxt_symbol = symbol[:3] + "/" + symbol[3:]
                
                order = await self._exchange.create_order(
                    symbol=ccxt_symbol,
                    type=type.lower(),
                    side=side.lower(),
                    amount=quantity,
                    price=price if type.upper() == "LIMIT" else None,
                )
                
                return {
                    "orderId": order['id'],
                    "symbol": symbol,
                    "side": side,
                    "type": type,
                    "quantity": quantity,
                    "price": price,
                    "status": order['status'],
                    "timestamp": order['timestamp'],
                }
                
            except Exception as e:
                logger.error(f"Failed to create order: {e}")
                raise
        
        return await self._create_paper_order(symbol, side, type, quantity, price)
    
    async def _create_paper_order(
        self,
        symbol: str,
        side: str,
        type: str,
        quantity: float,
        price: Optional[float]
    ) -> Dict[str, Any]:
        """Create a paper trading order."""
        order_id = str(self._paper_order_id)
        self._paper_order_id += 1
        
        if price is None:
            price = self._last_price.get(symbol.replace("USDT", "/USDT"), 50000.0)
        
        order = {
            "orderId": order_id,
            "symbol": symbol,
            "side": side,
            "type": type,
            "quantity": quantity,
            "price": price,
            "status": "NEW",
            "timestamp": int(time.time() * 1000),
            "filled": 0.0,
        }
        
        self._paper_orders[order_id] = order
        
        logger.info(f"Paper order created: {side} {quantity} {symbol} @ {price}")
        
        return order
    
    async def cancel_order(
        self,
        symbol: str,
        orderId: str
    ) -> Dict[str, Any]:
        """
        Cancel an order.
        
        Args:
            symbol: Trading pair
            orderId: Order ID to cancel
            
        Returns:
            Cancellation response
        """
        if self.paper_trading:
            if orderId in self._paper_orders:
                self._paper_orders[orderId]["status"] = "CANCELED"
                return {"orderId": orderId, "status": "CANCELED"}
            return {"orderId": orderId, "status": "NOT_FOUND"}
        
        if self._exchange:
            try:
                ccxt_symbol = symbol.replace("USDT", "/USDT")
                if "/" not in ccxt_symbol:
                    ccxt_symbol = symbol[:3] + "/" + symbol[3:]
                
                result = await self._exchange.cancel_order(orderId, ccxt_symbol)
                return {
                    "orderId": orderId,
                    "status": "CANCELED",
                    "result": result
                }
            except Exception as e:
                logger.error(f"Failed to cancel order: {e}")
                raise
        
        return {"orderId": orderId, "status": "CANCELED"}
    
    async def get_order(
        self,
        symbol: str,
        orderId: str
    ) -> Dict[str, Any]:
        """
        Get order status.
        
        Args:
            symbol: Trading pair
            orderId: Order ID
            
        Returns:
            Order status
        """
        if self.paper_trading:
            return self._paper_orders.get(orderId, {"status": "NOT_FOUND"})
        
        if self._exchange:
            try:
                ccxt_symbol = symbol.replace("USDT", "/USDT")
                if "/" not in ccxt_symbol:
                    ccxt_symbol = symbol[:3] + "/" + symbol[3:]
                
                order = await self._exchange.fetch_order(orderId, ccxt_symbol)
                return {
                    "orderId": order['id'],
                    "symbol": symbol,
                    "status": order['status'],
                    "filled": order['filled'],
                    "remaining": order['remaining'],
                    "price": order['price'],
                }
            except Exception as e:
                logger.error(f"Failed to get order: {e}")
        
        return {"orderId": orderId, "status": "UNKNOWN"}
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all open orders.
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of open orders
        """
        if self.paper_trading:
            orders = [
                o for o in self._paper_orders.values()
                if o["status"] in ["NEW", "PARTIALLY_FILLED"]
            ]
            if symbol:
                orders = [o for o in orders if o["symbol"] == symbol]
            return orders
        
        if self._exchange:
            try:
                ccxt_symbol = None
                if symbol:
                    ccxt_symbol = symbol.replace("USDT", "/USDT")
                    if "/" not in ccxt_symbol:
                        ccxt_symbol = symbol[:3] + "/" + symbol[3:]
                
                orders = await self._exchange.fetch_open_orders(ccxt_symbol)
                return [
                    {
                        "orderId": o['id'],
                        "symbol": o['symbol'],
                        "side": o['side'],
                        "type": o['type'],
                        "quantity": o['amount'],
                        "price": o['price'],
                        "status": o['status'],
                        "filled": o['filled'],
                    }
                    for o in orders
                ]
            except Exception as e:
                logger.error(f"Failed to get open orders: {e}")
        
        return []
    
    def on_price_update(self, callback: Callable) -> None:
        """Register callback for price updates."""
        self._price_callbacks.append(callback)
    
    def on_order_update(self, callback: Callable) -> None:
        """Register callback for order updates."""
        self._order_callbacks.append(callback)
    
    async def start_price_stream(self, symbols: List[str]) -> None:
        """
        Start WebSocket price stream for symbols.
        
        Args:
            symbols: List of symbols to stream
        """
        try:
            import websockets
            
            streams = [f"{s.lower().replace('/', '')}@ticker" for s in symbols]
            url = f"{self.ws_url}/{'/'.join(streams)}"
            
            async with websockets.connect(url) as ws:
                self._ws_connection = ws
                logger.info(f"WebSocket connected for {symbols}")
                
                async for message in ws:
                    data = json.loads(message)
                    
                    if 's' in data:
                        symbol = data['s']
                        price = float(data['c'])
                        self._last_price[symbol] = price
                        
                        for callback in self._price_callbacks:
                            try:
                                await callback(symbol, price, data)
                            except Exception as e:
                                logger.error(f"Price callback error: {e}")
                                
        except ImportError:
            logger.warning("websockets not available, price stream disabled")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
    
    async def simulate_price_update(self, symbol: str, price: float) -> None:
        """
        Simulate a price update (for paper trading).
        
        Args:
            symbol: Trading pair
            price: New price
        """
        self._last_price[symbol] = price
        
        for callback in self._price_callbacks:
            try:
                await callback(symbol, price, {"simulated": True})
            except Exception as e:
                logger.error(f"Price callback error: {e}")
        
        await self._check_paper_order_fills(symbol, price)
    
    async def _check_paper_order_fills(self, symbol: str, price: float) -> None:
        """Check if any paper orders should be filled at current price."""
        for order_id, order in list(self._paper_orders.items()):
            if order["status"] != "NEW":
                continue
            
            if order["symbol"].replace("/", "") != symbol.replace("/", ""):
                continue
            
            should_fill = False
            
            if order["side"] == "BUY" and price <= order["price"]:
                should_fill = True
            elif order["side"] == "SELL" and price >= order["price"]:
                should_fill = True
            
            if should_fill:
                order["status"] = "FILLED"
                order["filled"] = order["quantity"]
                
                if order["side"] == "BUY":
                    base = symbol.replace("/USDT", "").replace("USDT", "")
                    cost = order["quantity"] * order["price"]
                    self._paper_balance["USDT"] -= cost
                    self._paper_balance[base] = self._paper_balance.get(base, 0) + order["quantity"]
                else:
                    base = symbol.replace("/USDT", "").replace("USDT", "")
                    revenue = order["quantity"] * order["price"]
                    self._paper_balance["USDT"] += revenue
                    self._paper_balance[base] = self._paper_balance.get(base, 0) - order["quantity"]
                
                for callback in self._order_callbacks:
                    try:
                        await callback(order)
                    except Exception as e:
                        logger.error(f"Order callback error: {e}")
                
                logger.info(f"Paper order filled: {order_id} @ {price}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get connector status."""
        return {
            "connected": self._is_connected,
            "paper_trading": self.paper_trading,
            "testnet": self.config.testnet,
            "has_exchange": self._exchange is not None,
            "last_prices": self._last_price.copy(),
            "paper_balance": self._paper_balance.copy() if self.paper_trading else None,
            "open_paper_orders": len([
                o for o in self._paper_orders.values()
                if o["status"] == "NEW"
            ]) if self.paper_trading else None,
        }
