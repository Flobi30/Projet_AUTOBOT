import os
import logging
import ccxt
from typing import Dict, Any, Optional, List, Union
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

class CCXTProvider:
    """
    Enhanced CCXT provider for cryptocurrency exchange integration.
    """
    
    def __init__(
        self, 
        exchange_id: str = 'binance',
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        sandbox: bool = False,
        timeout: int = 30000,
        enableRateLimit: bool = True
    ):
        """
        Initialize the CCXT provider.
        
        Args:
            exchange_id: ID of the exchange to use (e.g., 'binance', 'coinbase', 'kraken')
            api_key: API key for authenticated requests
            api_secret: API secret for authenticated requests
            sandbox: Whether to use the sandbox/testnet environment
            timeout: Request timeout in milliseconds
            enableRateLimit: Whether to enable the built-in rate limiter
        """
        self.exchange_id = exchange_id
        
        self.api_key = api_key or os.getenv(f"{exchange_id.upper()}_API_KEY")
        self.api_secret = api_secret or os.getenv(f"{exchange_id.upper()}_API_SECRET")
        
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'timeout': timeout,
            'enableRateLimit': enableRateLimit
        })
        
        if sandbox and self.exchange.has['test']:
            self.exchange.set_sandbox_mode(True)
            
        logger.info(f"Initialized CCXT provider for {exchange_id}")
    
    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch current ticker data for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            
        Returns:
            Dict: Ticker data
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            logger.debug(f"Fetched ticker for {symbol}: {ticker['last']}")
            return ticker
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {str(e)}")
            raise
    
    def fetch_ohlcv(
        self, 
        symbol: str, 
        timeframe: str = '1h', 
        limit: int = 100,
        since: Optional[int] = None
    ) -> List[List[float]]:
        """
        Fetch OHLCV (Open, High, Low, Close, Volume) data.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            timeframe: Timeframe for data (e.g., '1m', '5m', '1h', '1d')
            limit: Number of candles to fetch
            since: Timestamp in milliseconds for the earliest data point
            
        Returns:
            List: List of OHLCV candles
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since, limit)
            logger.debug(f"Fetched {len(ohlcv)} OHLCV candles for {symbol} on {timeframe} timeframe")
            return ohlcv
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol}: {str(e)}")
            raise
    
    def fetch_ohlcv_as_df(
        self, 
        symbol: str, 
        timeframe: str = '1h', 
        limit: int = 100,
        since: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data and return as a pandas DataFrame.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            timeframe: Timeframe for data (e.g., '1m', '5m', '1h', '1d')
            limit: Number of candles to fetch
            since: Timestamp in milliseconds for the earliest data point
            
        Returns:
            DataFrame: OHLCV data as a pandas DataFrame
        """
        ohlcv = self.fetch_ohlcv(symbol, timeframe, limit, since)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    
    def fetch_order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """
        Fetch order book for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            limit: Number of orders to fetch
            
        Returns:
            Dict: Order book data
        """
        try:
            order_book = self.exchange.fetch_order_book(symbol, limit)
            logger.debug(f"Fetched order book for {symbol} with {len(order_book['bids'])} bids and {len(order_book['asks'])} asks")
            return order_book
        except Exception as e:
            logger.error(f"Error fetching order book for {symbol}: {str(e)}")
            raise
    
    def create_order(
        self, 
        symbol: str, 
        order_type: str, 
        side: str, 
        amount: float, 
        price: Optional[float] = None,
        params: Dict[str, Any] = {}
    ) -> Dict[str, Any]:
        """
        Create a new order.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            order_type: Type of order ('limit', 'market')
            side: Order side ('buy', 'sell')
            amount: Amount of base currency to trade
            price: Price for limit orders
            params: Additional parameters for the exchange API
            
        Returns:
            Dict: Order information
        """
        try:
            if not self.api_key or not self.api_secret:
                raise ValueError("API key and secret are required for trading operations")
                
            order = self.exchange.create_order(symbol, order_type, side, amount, price, params)
            logger.info(f"Created {order_type} {side} order for {amount} {symbol} at {price}: {order['id']}")
            return order
        except Exception as e:
            logger.error(f"Error creating order for {symbol}: {str(e)}")
            raise
    
    def cancel_order(self, order_id: str, symbol: str, params: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Cancel an existing order.
        
        Args:
            order_id: ID of the order to cancel
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            params: Additional parameters for the exchange API
            
        Returns:
            Dict: Cancellation result
        """
        try:
            if not self.api_key or not self.api_secret:
                raise ValueError("API key and secret are required for trading operations")
                
            result = self.exchange.cancel_order(order_id, symbol, params)
            logger.info(f"Cancelled order {order_id} for {symbol}")
            return result
        except Exception as e:
            logger.error(f"Error cancelling order {order_id} for {symbol}: {str(e)}")
            raise
    
    def fetch_balance(self) -> Dict[str, Any]:
        """
        Fetch account balance.
        
        Returns:
            Dict: Account balance information
        """
        try:
            if not self.api_key or not self.api_secret:
                raise ValueError("API key and secret are required for account operations")
                
            balance = self.exchange.fetch_balance()
            logger.debug(f"Fetched account balance: {balance['total']}")
            return balance
        except Exception as e:
            logger.error(f"Error fetching account balance: {str(e)}")
            raise
    
    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch open orders.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            
        Returns:
            List: List of open orders
        """
        try:
            if not self.api_key or not self.api_secret:
                raise ValueError("API key and secret are required for account operations")
                
            orders = self.exchange.fetch_open_orders(symbol)
            logger.debug(f"Fetched {len(orders)} open orders" + (f" for {symbol}" if symbol else ""))
            return orders
        except Exception as e:
            logger.error(f"Error fetching open orders: {str(e)}")
            raise
    
    def get_supported_exchanges() -> List[str]:
        """
        Get a list of supported exchanges.
        
        Returns:
            List: List of supported exchange IDs
        """
        return ccxt.exchanges

def get_ccxt_provider(exchange_id: str = 'binance', **kwargs) -> CCXTProvider:
    """
    Get a CCXT provider instance.
    
    Args:
        exchange_id: ID of the exchange to use
        **kwargs: Additional parameters for the CCXTProvider
        
    Returns:
        CCXTProvider: CCXT provider instance
    """
    return CCXTProvider(exchange_id, **kwargs)

def fetch_ticker(symbol: str, exchange_id: str = 'binance', **kwargs) -> Dict[str, Any]:
    """
    Fetch ticker data for a symbol.
    
    Args:
        symbol: Trading pair symbol (e.g., 'BTC/USDT')
        exchange_id: ID of the exchange to use
        **kwargs: Additional parameters for the CCXTProvider
        
    Returns:
        Dict: Ticker data
    """
    provider = get_ccxt_provider(exchange_id, **kwargs)
    return provider.fetch_ticker(symbol)
