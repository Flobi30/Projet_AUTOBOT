"""
Interactive Brokers TWS API Connector.

Event-driven connector for Interactive Brokers TWS/Gateway.
Supports real-time market data, historical data, and order execution.
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set
from queue import Queue, Empty

from .base import (
    BaseConnector,
    ConnectionStatus,
    ConnectorEvent,
    EventType,
    MarketData,
)
from .rate_limiter import RateLimiter, RateLimitConfig
from .cache import MarketDataCache, CacheConfig
from .validator import DataValidator, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class IBConfig:
    """Configuration for Interactive Brokers connector."""
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1
    
    auto_reconnect: bool = True
    reconnect_delay: float = 5.0
    max_reconnect_attempts: int = 10
    
    request_timeout: float = 30.0
    heartbeat_interval: float = 30.0
    
    use_cache: bool = True
    cache_ttl: float = 1.0
    
    use_rate_limiter: bool = True
    requests_per_second: float = 50.0
    
    validate_data: bool = True
    
    account: str = ""
    read_only: bool = True


class IBMessageType:
    """IB API message types."""
    TICK_PRICE = 1
    TICK_SIZE = 2
    TICK_STRING = 46
    TICK_GENERIC = 45
    TICK_EFP = 47
    ORDER_STATUS = 3
    ERROR = 4
    OPEN_ORDER = 5
    ACCOUNT_VALUE = 6
    PORTFOLIO_VALUE = 7
    ACCOUNT_UPDATE_TIME = 8
    NEXT_VALID_ID = 9
    CONTRACT_DATA = 10
    EXECUTION_DATA = 11
    MARKET_DEPTH = 12
    MARKET_DEPTH_L2 = 13
    NEWS_BULLETINS = 14
    MANAGED_ACCOUNTS = 15
    RECEIVE_FA = 16
    HISTORICAL_DATA = 17
    BOND_CONTRACT_DATA = 18
    SCANNER_PARAMETERS = 19
    SCANNER_DATA = 20
    TICK_OPTION_COMPUTATION = 21
    TICK_GENERIC_DOUBLE = 45
    TICK_STRING_MSG = 46
    TICK_EFP_MSG = 47
    CURRENT_TIME = 49
    REAL_TIME_BARS = 50
    FUNDAMENTAL_DATA = 51
    CONTRACT_DATA_END = 52
    OPEN_ORDER_END = 53
    ACCOUNT_DOWNLOAD_END = 54
    EXECUTION_DATA_END = 55
    DELTA_NEUTRAL_VALIDATION = 56
    TICK_SNAPSHOT_END = 57
    MARKET_DATA_TYPE = 58
    COMMISSION_REPORT = 59
    POSITION = 61
    POSITION_END = 62
    ACCOUNT_SUMMARY = 63
    ACCOUNT_SUMMARY_END = 64
    VERIFY_MESSAGE_API = 65
    VERIFY_COMPLETED = 66
    DISPLAY_GROUP_LIST = 67
    DISPLAY_GROUP_UPDATED = 68
    VERIFY_AND_AUTH_MESSAGE_API = 69
    VERIFY_AND_AUTH_COMPLETED = 70
    POSITION_MULTI = 71
    POSITION_MULTI_END = 72
    ACCOUNT_UPDATE_MULTI = 73
    ACCOUNT_UPDATE_MULTI_END = 74


class IBTickType:
    """IB tick types for market data."""
    BID_SIZE = 0
    BID = 1
    ASK = 2
    ASK_SIZE = 3
    LAST = 4
    LAST_SIZE = 5
    HIGH = 6
    LOW = 7
    VOLUME = 8
    CLOSE = 9
    BID_OPTION = 10
    ASK_OPTION = 11
    LAST_OPTION = 12
    MODEL_OPTION = 13
    OPEN = 14
    LOW_13_WEEK = 15
    HIGH_13_WEEK = 16
    LOW_26_WEEK = 17
    HIGH_26_WEEK = 18
    LOW_52_WEEK = 19
    HIGH_52_WEEK = 20
    AVG_VOLUME = 21
    OPEN_INTEREST = 22
    OPTION_HISTORICAL_VOL = 23
    OPTION_IMPLIED_VOL = 24
    OPTION_BID_EXCH = 25
    OPTION_ASK_EXCH = 26
    OPTION_CALL_OPEN_INTEREST = 27
    OPTION_PUT_OPEN_INTEREST = 28
    OPTION_CALL_VOLUME = 29
    OPTION_PUT_VOLUME = 30
    INDEX_FUTURE_PREMIUM = 31
    BID_EXCH = 32
    ASK_EXCH = 33
    AUCTION_VOLUME = 34
    AUCTION_PRICE = 35
    AUCTION_IMBALANCE = 36
    MARK_PRICE = 37
    BID_EFP_COMPUTATION = 38
    ASK_EFP_COMPUTATION = 39
    LAST_EFP_COMPUTATION = 40
    OPEN_EFP_COMPUTATION = 41
    HIGH_EFP_COMPUTATION = 42
    LOW_EFP_COMPUTATION = 43
    CLOSE_EFP_COMPUTATION = 44
    LAST_TIMESTAMP = 45
    SHORTABLE = 46
    FUNDAMENTAL_RATIOS = 47
    RT_VOLUME = 48
    HALTED = 49
    BID_YIELD = 50
    ASK_YIELD = 51
    LAST_YIELD = 52
    CUST_OPTION_COMPUTATION = 53
    TRADE_COUNT = 54
    TRADE_RATE = 55
    VOLUME_RATE = 56
    LAST_RTH_TRADE = 57
    RT_HISTORICAL_VOL = 58


@dataclass
class IBContract:
    """IB Contract specification."""
    symbol: str
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"
    primary_exchange: str = ""
    local_symbol: str = ""
    con_id: int = 0
    multiplier: str = ""
    expiry: str = ""
    strike: float = 0.0
    right: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "secType": self.sec_type,
            "exchange": self.exchange,
            "currency": self.currency,
            "primaryExchange": self.primary_exchange,
            "localSymbol": self.local_symbol,
            "conId": self.con_id,
            "multiplier": self.multiplier,
            "expiry": self.expiry,
            "strike": self.strike,
            "right": self.right,
        }


class IBConnector(BaseConnector):
    """
    Interactive Brokers TWS API Connector.
    
    Event-driven connector supporting:
    - Real-time market data streaming
    - Historical data requests
    - Order management (if not read-only)
    - Account information
    - Rate limiting and caching
    - Data validation
    
    Note: This is a simulation/mock implementation.
    For production use, integrate with ib_insync or ibapi library.
    """
    
    def __init__(self, config: Optional[IBConfig] = None):
        self.config = config or IBConfig()
        
        super().__init__(
            name="interactive_brokers",
            auto_reconnect=self.config.auto_reconnect,
            reconnect_delay=self.config.reconnect_delay,
            max_reconnect_attempts=self.config.max_reconnect_attempts,
            heartbeat_interval=self.config.heartbeat_interval,
        )
        
        self._next_req_id = 1
        self._req_id_lock = threading.Lock()
        
        self._market_data: Dict[str, MarketData] = {}
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._symbol_to_req_id: Dict[str, int] = {}
        self._req_id_to_symbol: Dict[int, str] = {}
        
        self._contracts: Dict[str, IBContract] = {}
        
        self._message_queue: Queue = Queue()
        self._reader_thread: Optional[threading.Thread] = None
        
        if self.config.use_rate_limiter:
            self._rate_limiter = RateLimiter(
                config=RateLimitConfig(
                    requests_per_second=self.config.requests_per_second,
                    burst_size=100,
                ),
                name="ib_connector",
            )
        else:
            self._rate_limiter = None
        
        if self.config.use_cache:
            self._cache = MarketDataCache(
                config=CacheConfig(
                    default_ttl=self.config.cache_ttl,
                    symbol_ttl=self.config.cache_ttl,
                    historical_ttl=3600.0,
                )
            )
        else:
            self._cache = None
        
        if self.config.validate_data:
            self._validator = DataValidator(strict_mode=False)
        else:
            self._validator = None
        
        self._connection = None
        self._connected_event = asyncio.Event()
        
        logger.info(f"IBConnector initialized: {self.config.host}:{self.config.port}")
    
    def _get_next_req_id(self) -> int:
        """Get next request ID (thread-safe)."""
        with self._req_id_lock:
            req_id = self._next_req_id
            self._next_req_id += 1
            return req_id
    
    def _parse_symbol(self, symbol: str) -> IBContract:
        """
        Parse symbol string to IBContract.
        
        Supports formats:
        - "AAPL" -> Stock on SMART
        - "AAPL:NASDAQ" -> Stock on specific exchange
        - "EUR.USD" or "EUR/USD" -> Forex
        - "ES:GLOBEX:FUT:202312" -> Future
        """
        if symbol in self._contracts:
            return self._contracts[symbol]
        
        parts = symbol.replace("/", ".").split(":")
        
        if len(parts) == 1:
            base_symbol = parts[0]
            if "." in base_symbol:
                contract = IBContract(
                    symbol=base_symbol,
                    sec_type="CASH",
                    exchange="IDEALPRO",
                    currency=base_symbol.split(".")[1] if "." in base_symbol else "USD",
                )
            else:
                contract = IBContract(symbol=base_symbol)
        
        elif len(parts) == 2:
            contract = IBContract(
                symbol=parts[0],
                exchange=parts[1],
            )
        
        elif len(parts) >= 3:
            contract = IBContract(
                symbol=parts[0],
                exchange=parts[1],
                sec_type=parts[2] if len(parts) > 2 else "STK",
                expiry=parts[3] if len(parts) > 3 else "",
            )
        
        else:
            contract = IBContract(symbol=symbol)
        
        self._contracts[symbol] = contract
        return contract
    
    async def connect(self) -> bool:
        """
        Connect to TWS/Gateway.
        
        Returns:
            bool: True if connection successful
        """
        if self.is_connected:
            return True
        
        self.status = ConnectionStatus.CONNECTING
        
        try:
            logger.info(f"Connecting to IB TWS at {self.config.host}:{self.config.port}")
            
            await asyncio.sleep(0.1)
            
            self._connected_event.set()
            self.status = ConnectionStatus.CONNECTED
            
            self._emit_event(
                EventType.CONNECTED,
                metadata={
                    "host": self.config.host,
                    "port": self.config.port,
                    "client_id": self.config.client_id,
                }
            )
            
            logger.info("Connected to IB TWS")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to IB TWS: {e}")
            self.status = ConnectionStatus.ERROR
            self._emit_event(EventType.ERROR, error=str(e))
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from TWS/Gateway."""
        if not self.is_connected:
            return
        
        try:
            for symbol in list(self._subscriptions):
                await self.unsubscribe(symbol)
            
            self._connected_event.clear()
            self.status = ConnectionStatus.DISCONNECTED
            
            self._emit_event(EventType.DISCONNECTED)
            logger.info("Disconnected from IB TWS")
            
        except Exception as e:
            logger.error(f"Error disconnecting from IB TWS: {e}")
            self._emit_event(EventType.ERROR, error=str(e))
    
    async def subscribe(self, symbol: str) -> bool:
        """
        Subscribe to real-time market data.
        
        Args:
            symbol: Symbol to subscribe to
            
        Returns:
            bool: True if subscription successful
        """
        if not self.is_connected:
            logger.warning(f"Cannot subscribe to {symbol}: not connected")
            return False
        
        if symbol in self._subscriptions:
            return True
        
        if self._rate_limiter:
            acquired = await self._rate_limiter.wait_and_acquire("subscribe")
            if not acquired:
                logger.warning(f"Rate limited: cannot subscribe to {symbol}")
                self._emit_event(EventType.RATE_LIMITED, metadata={"symbol": symbol})
                return False
        
        try:
            contract = self._parse_symbol(symbol)
            req_id = self._get_next_req_id()
            
            self._symbol_to_req_id[symbol] = req_id
            self._req_id_to_symbol[req_id] = symbol
            
            self._market_data[symbol] = MarketData(
                symbol=symbol,
                timestamp=datetime.utcnow(),
                source="interactive_brokers",
            )
            
            with self._lock:
                self._subscriptions.add(symbol)
            
            self._emit_event(
                EventType.SUBSCRIPTION_ADDED,
                data={"symbol": symbol, "req_id": req_id},
            )
            
            logger.info(f"Subscribed to {symbol} (req_id={req_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to subscribe to {symbol}: {e}")
            self._emit_event(EventType.ERROR, error=str(e), metadata={"symbol": symbol})
            return False
    
    async def unsubscribe(self, symbol: str) -> bool:
        """
        Unsubscribe from market data.
        
        Args:
            symbol: Symbol to unsubscribe from
            
        Returns:
            bool: True if unsubscription successful
        """
        if symbol not in self._subscriptions:
            return True
        
        try:
            req_id = self._symbol_to_req_id.get(symbol)
            
            if req_id:
                del self._symbol_to_req_id[symbol]
                del self._req_id_to_symbol[req_id]
            
            with self._lock:
                self._subscriptions.discard(symbol)
            
            self._market_data.pop(symbol, None)
            
            self._emit_event(
                EventType.SUBSCRIPTION_REMOVED,
                data={"symbol": symbol},
            )
            
            logger.info(f"Unsubscribed from {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unsubscribe from {symbol}: {e}")
            return False
    
    async def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """
        Get current market data for a symbol.
        
        Args:
            symbol: Symbol to get data for
            
        Returns:
            MarketData or None if not available
        """
        if self._cache:
            cached = self._cache.get_symbol_data(symbol, "ib")
            if cached:
                self._emit_event(EventType.CACHE_HIT, metadata={"symbol": symbol})
                return cached
            self._emit_event(EventType.CACHE_MISS, metadata={"symbol": symbol})
        
        if symbol in self._market_data:
            data = self._market_data[symbol]
            
            if self._validator:
                result = self._validator.validate(data)
                if not result.is_valid:
                    self._emit_event(
                        EventType.VALIDATION_FAILED,
                        data=result,
                        metadata={"symbol": symbol},
                    )
                else:
                    self._emit_event(EventType.VALIDATION_PASSED, metadata={"symbol": symbol})
            
            if self._cache:
                self._cache.set_symbol_data(symbol, data, "ib")
            
            return data
        
        if symbol not in self._subscriptions:
            await self.subscribe(symbol)
            await asyncio.sleep(0.5)
            return self._market_data.get(symbol)
        
        return None
    
    async def get_historical_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m",
    ) -> List[MarketData]:
        """
        Get historical market data.
        
        Args:
            symbol: Symbol to get data for
            start: Start datetime
            end: End datetime
            interval: Data interval (e.g., "1m", "5m", "1h", "1d")
            
        Returns:
            List of MarketData objects
        """
        if self._cache:
            cached = self._cache.get_historical_data(symbol, start, end, interval, "ib")
            if cached:
                self._emit_event(EventType.CACHE_HIT, metadata={"symbol": symbol, "type": "historical"})
                return cached
        
        if not self.is_connected:
            logger.warning(f"Cannot get historical data for {symbol}: not connected")
            return []
        
        if self._rate_limiter:
            acquired = await self._rate_limiter.wait_and_acquire("historical")
            if not acquired:
                logger.warning(f"Rate limited: cannot get historical data for {symbol}")
                return []
        
        try:
            contract = self._parse_symbol(symbol)
            req_id = self._get_next_req_id()
            
            interval_map = {
                "1s": "1 secs",
                "5s": "5 secs",
                "10s": "10 secs",
                "15s": "15 secs",
                "30s": "30 secs",
                "1m": "1 min",
                "2m": "2 mins",
                "3m": "3 mins",
                "5m": "5 mins",
                "10m": "10 mins",
                "15m": "15 mins",
                "20m": "20 mins",
                "30m": "30 mins",
                "1h": "1 hour",
                "2h": "2 hours",
                "3h": "3 hours",
                "4h": "4 hours",
                "8h": "8 hours",
                "1d": "1 day",
                "1w": "1 week",
                "1M": "1 month",
            }
            
            ib_interval = interval_map.get(interval, "1 min")
            
            duration = end - start
            if duration.days > 365:
                duration_str = f"{duration.days // 365} Y"
            elif duration.days > 30:
                duration_str = f"{duration.days // 30} M"
            elif duration.days > 0:
                duration_str = f"{duration.days} D"
            else:
                duration_str = f"{int(duration.total_seconds())} S"
            
            logger.info(f"Requesting historical data for {symbol}: {duration_str}, {ib_interval}")
            
            result: List[MarketData] = []
            
            current = start
            while current < end:
                data = MarketData(
                    symbol=symbol,
                    timestamp=current,
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.5,
                    volume=10000.0,
                    source="interactive_brokers",
                )
                result.append(data)
                
                if "s" in interval:
                    seconds = int(interval.replace("s", ""))
                    current += timedelta(seconds=seconds)
                elif "m" in interval:
                    minutes = int(interval.replace("m", ""))
                    current += timedelta(minutes=minutes)
                elif "h" in interval:
                    hours = int(interval.replace("h", ""))
                    current += timedelta(hours=hours)
                elif "d" in interval:
                    days = int(interval.replace("d", ""))
                    current += timedelta(days=days)
                else:
                    current += timedelta(minutes=1)
            
            if self._cache:
                self._cache.set_historical_data(symbol, start, end, interval, result, "ib")
            
            self._emit_event(
                EventType.DATA_RECEIVED,
                data={"symbol": symbol, "count": len(result), "type": "historical"},
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get historical data for {symbol}: {e}")
            self._emit_event(EventType.ERROR, error=str(e), metadata={"symbol": symbol})
            return []
    
    def _handle_tick_price(self, req_id: int, tick_type: int, price: float) -> None:
        """Handle incoming tick price."""
        symbol = self._req_id_to_symbol.get(req_id)
        if not symbol or symbol not in self._market_data:
            return
        
        data = self._market_data[symbol]
        data.timestamp = datetime.utcnow()
        
        if tick_type == IBTickType.BID:
            data.bid = price
        elif tick_type == IBTickType.ASK:
            data.ask = price
        elif tick_type == IBTickType.LAST:
            data.last = price
        elif tick_type == IBTickType.HIGH:
            data.high = price
        elif tick_type == IBTickType.LOW:
            data.low = price
        elif tick_type == IBTickType.OPEN:
            data.open = price
        elif tick_type == IBTickType.CLOSE:
            data.close = price
        
        self._emit_event(
            EventType.DATA_RECEIVED,
            data=data,
            metadata={"symbol": symbol, "tick_type": tick_type},
        )
    
    def _handle_tick_size(self, req_id: int, tick_type: int, size: int) -> None:
        """Handle incoming tick size."""
        symbol = self._req_id_to_symbol.get(req_id)
        if not symbol or symbol not in self._market_data:
            return
        
        data = self._market_data[symbol]
        
        if tick_type == IBTickType.VOLUME:
            data.volume = float(size)
            data.timestamp = datetime.utcnow()
    
    async def request_contract_details(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Request contract details for a symbol.
        
        Args:
            symbol: Symbol to get details for
            
        Returns:
            Contract details dictionary or None
        """
        if not self.is_connected:
            return None
        
        contract = self._parse_symbol(symbol)
        
        return {
            "symbol": contract.symbol,
            "secType": contract.sec_type,
            "exchange": contract.exchange,
            "currency": contract.currency,
            "minTick": 0.01,
            "tradingHours": "20230101:0930-20230101:1600",
            "liquidHours": "20230101:0930-20230101:1600",
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connector statistics."""
        stats = super().get_stats()
        
        stats.update({
            "host": self.config.host,
            "port": self.config.port,
            "client_id": self.config.client_id,
            "read_only": self.config.read_only,
            "next_req_id": self._next_req_id,
            "active_subscriptions": len(self._subscriptions),
            "cached_symbols": len(self._market_data),
        })
        
        if self._rate_limiter:
            stats["rate_limiter"] = self._rate_limiter.get_stats()
        
        if self._cache:
            stats["cache"] = self._cache.get_stats()
        
        return stats


def create_ib_connector(
    host: str = "127.0.0.1",
    port: int = 7497,
    client_id: int = 1,
    **kwargs,
) -> IBConnector:
    """
    Factory function to create an IB connector.
    
    Args:
        host: TWS/Gateway host
        port: TWS/Gateway port (7497 for TWS paper, 7496 for TWS live, 4002 for Gateway)
        client_id: Client ID for connection
        **kwargs: Additional IBConfig parameters
        
    Returns:
        Configured IBConnector instance
    """
    config = IBConfig(
        host=host,
        port=port,
        client_id=client_id,
        **kwargs,
    )
    return IBConnector(config)
