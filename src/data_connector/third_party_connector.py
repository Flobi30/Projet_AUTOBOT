"""
Third Party Data Connector.

Unified connector for multiple third-party data providers.
Supports simultaneous data collection from all configured APIs.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Union
import aiohttp

from .base import (
    BaseConnector,
    ConnectionStatus,
    ConnectorEvent,
    EventType,
    MarketData,
)
from .rate_limiter import MultiProviderRateLimiter, RateLimiter, RateLimitConfig
from .cache import MarketDataCache, CacheConfig
from .validator import DataValidator, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class ThirdPartyConfig:
    """Configuration for third-party data connector."""
    providers: List[str] = field(default_factory=lambda: [
        "twelvedata", "alphavantage", "binance", "coinbase", "kraken", "fred", "newsapi"
    ])
    
    simultaneous_collection: bool = True
    
    auto_reconnect: bool = True
    reconnect_delay: float = 5.0
    max_reconnect_attempts: int = 10
    
    request_timeout: float = 30.0
    heartbeat_interval: float = 30.0
    
    use_cache: bool = True
    cache_ttl: float = 60.0
    
    use_rate_limiter: bool = True
    validate_data: bool = True
    
    twelvedata_api_key: str = ""
    alphavantage_api_key: str = ""
    binance_api_key: str = ""
    binance_api_secret: str = ""
    coinbase_api_key: str = ""
    coinbase_api_secret: str = ""
    kraken_api_key: str = ""
    kraken_api_secret: str = ""
    fred_api_key: str = ""
    newsapi_api_key: str = ""
    
    def __post_init__(self):
        if not self.twelvedata_api_key:
            self.twelvedata_api_key = os.getenv("TWELVEDATA_API_KEY", "")
        if not self.alphavantage_api_key:
            self.alphavantage_api_key = os.getenv("ALPHAVANTAGE_API_KEY", "")
        if not self.binance_api_key:
            self.binance_api_key = os.getenv("BINANCE_API_KEY", "")
        if not self.binance_api_secret:
            self.binance_api_secret = os.getenv("BINANCE_API_SECRET", "")
        if not self.coinbase_api_key:
            self.coinbase_api_key = os.getenv("COINBASE_API_KEY", "")
        if not self.coinbase_api_secret:
            self.coinbase_api_secret = os.getenv("COINBASE_API_SECRET", "")
        if not self.kraken_api_key:
            self.kraken_api_key = os.getenv("KRAKEN_API_KEY", "")
        if not self.kraken_api_secret:
            self.kraken_api_secret = os.getenv("KRAKEN_API_SECRET", "")
        if not self.fred_api_key:
            self.fred_api_key = os.getenv("FRED_API_KEY", "")
        if not self.newsapi_api_key:
            self.newsapi_api_key = os.getenv("NEWSAPI_API_KEY", "")


class ProviderAdapter:
    """Base adapter for data providers."""
    
    def __init__(self, name: str, api_key: str = "", api_secret: str = ""):
        self.name = name
        self.api_key = api_key
        self.api_secret = api_secret
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session
    
    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def get_quote(self, symbol: str) -> Optional[MarketData]:
        """Get current quote for a symbol."""
        raise NotImplementedError
    
    async def get_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str,
    ) -> List[MarketData]:
        """Get historical data for a symbol."""
        raise NotImplementedError
    
    def is_configured(self) -> bool:
        """Check if provider is properly configured."""
        return bool(self.api_key)


class TwelveDataAdapter(ProviderAdapter):
    """Adapter for TwelveData API."""
    
    BASE_URL = "https://api.twelvedata.com"
    
    def __init__(self, api_key: str = ""):
        super().__init__("twelvedata", api_key)
    
    async def get_quote(self, symbol: str) -> Optional[MarketData]:
        """Get current quote from TwelveData."""
        if not self.is_configured():
            return None
        
        try:
            session = await self._get_session()
            url = f"{self.BASE_URL}/quote"
            params = {
                "symbol": symbol,
                "apikey": self.api_key,
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if "code" in data:
                        logger.warning(f"TwelveData error: {data.get('message', 'Unknown error')}")
                        return None
                    
                    return MarketData(
                        symbol=symbol,
                        timestamp=datetime.utcnow(),
                        open=float(data.get("open", 0)) if data.get("open") else None,
                        high=float(data.get("high", 0)) if data.get("high") else None,
                        low=float(data.get("low", 0)) if data.get("low") else None,
                        close=float(data.get("close", 0)) if data.get("close") else None,
                        volume=float(data.get("volume", 0)) if data.get("volume") else None,
                        source="twelvedata",
                        raw_data=data,
                    )
                elif response.status == 429:
                    logger.warning("TwelveData rate limit exceeded")
                    return None
                else:
                    logger.error(f"TwelveData request failed: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"TwelveData error: {e}")
            return None
    
    async def get_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str,
    ) -> List[MarketData]:
        """Get historical data from TwelveData."""
        if not self.is_configured():
            return []
        
        try:
            session = await self._get_session()
            url = f"{self.BASE_URL}/time_series"
            
            interval_map = {
                "1m": "1min",
                "5m": "5min",
                "15m": "15min",
                "30m": "30min",
                "1h": "1h",
                "4h": "4h",
                "1d": "1day",
                "1w": "1week",
                "1M": "1month",
            }
            
            params = {
                "symbol": symbol,
                "interval": interval_map.get(interval, "1min"),
                "start_date": start.strftime("%Y-%m-%d %H:%M:%S"),
                "end_date": end.strftime("%Y-%m-%d %H:%M:%S"),
                "apikey": self.api_key,
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if "code" in data:
                        logger.warning(f"TwelveData error: {data.get('message', 'Unknown error')}")
                        return []
                    
                    values = data.get("values", [])
                    result = []
                    
                    for item in values:
                        try:
                            result.append(MarketData(
                                symbol=symbol,
                                timestamp=datetime.fromisoformat(item["datetime"]),
                                open=float(item.get("open", 0)),
                                high=float(item.get("high", 0)),
                                low=float(item.get("low", 0)),
                                close=float(item.get("close", 0)),
                                volume=float(item.get("volume", 0)) if item.get("volume") else None,
                                source="twelvedata",
                            ))
                        except (ValueError, KeyError) as e:
                            logger.warning(f"Failed to parse TwelveData item: {e}")
                    
                    return result
                else:
                    logger.error(f"TwelveData historical request failed: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"TwelveData historical error: {e}")
            return []


class AlphaVantageAdapter(ProviderAdapter):
    """Adapter for Alpha Vantage API."""
    
    BASE_URL = "https://www.alphavantage.co/query"
    
    def __init__(self, api_key: str = ""):
        super().__init__("alphavantage", api_key)
    
    async def get_quote(self, symbol: str) -> Optional[MarketData]:
        """Get current quote from Alpha Vantage."""
        if not self.is_configured():
            return None
        
        try:
            session = await self._get_session()
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": symbol,
                "apikey": self.api_key,
            }
            
            async with session.get(self.BASE_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if "Note" in data:
                        logger.warning("Alpha Vantage rate limit exceeded")
                        return None
                    
                    quote = data.get("Global Quote", {})
                    if not quote:
                        return None
                    
                    return MarketData(
                        symbol=symbol,
                        timestamp=datetime.utcnow(),
                        open=float(quote.get("02. open", 0)) if quote.get("02. open") else None,
                        high=float(quote.get("03. high", 0)) if quote.get("03. high") else None,
                        low=float(quote.get("04. low", 0)) if quote.get("04. low") else None,
                        last=float(quote.get("05. price", 0)) if quote.get("05. price") else None,
                        close=float(quote.get("08. previous close", 0)) if quote.get("08. previous close") else None,
                        volume=float(quote.get("06. volume", 0)) if quote.get("06. volume") else None,
                        source="alphavantage",
                        raw_data=quote,
                    )
                else:
                    logger.error(f"Alpha Vantage request failed: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Alpha Vantage error: {e}")
            return None
    
    async def get_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str,
    ) -> List[MarketData]:
        """Get historical data from Alpha Vantage."""
        if not self.is_configured():
            return []
        
        try:
            session = await self._get_session()
            
            if interval in ["1m", "5m", "15m", "30m", "1h"]:
                function = "TIME_SERIES_INTRADAY"
                interval_map = {
                    "1m": "1min",
                    "5m": "5min",
                    "15m": "15min",
                    "30m": "30min",
                    "1h": "60min",
                }
                params = {
                    "function": function,
                    "symbol": symbol,
                    "interval": interval_map.get(interval, "1min"),
                    "outputsize": "full",
                    "apikey": self.api_key,
                }
            else:
                function = "TIME_SERIES_DAILY"
                params = {
                    "function": function,
                    "symbol": symbol,
                    "outputsize": "full",
                    "apikey": self.api_key,
                }
            
            async with session.get(self.BASE_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if "Note" in data:
                        logger.warning("Alpha Vantage rate limit exceeded")
                        return []
                    
                    time_series_key = None
                    for key in data.keys():
                        if "Time Series" in key:
                            time_series_key = key
                            break
                    
                    if not time_series_key:
                        return []
                    
                    time_series = data[time_series_key]
                    result = []
                    
                    for timestamp_str, values in time_series.items():
                        try:
                            timestamp = datetime.fromisoformat(timestamp_str)
                            
                            if start <= timestamp <= end:
                                result.append(MarketData(
                                    symbol=symbol,
                                    timestamp=timestamp,
                                    open=float(values.get("1. open", 0)),
                                    high=float(values.get("2. high", 0)),
                                    low=float(values.get("3. low", 0)),
                                    close=float(values.get("4. close", 0)),
                                    volume=float(values.get("5. volume", 0)) if values.get("5. volume") else None,
                                    source="alphavantage",
                                ))
                        except (ValueError, KeyError) as e:
                            logger.warning(f"Failed to parse Alpha Vantage item: {e}")
                    
                    result.sort(key=lambda x: x.timestamp)
                    return result
                else:
                    logger.error(f"Alpha Vantage historical request failed: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Alpha Vantage historical error: {e}")
            return []


class BinanceAdapter(ProviderAdapter):
    """Adapter for Binance API."""
    
    BASE_URL = "https://api.binance.com/api/v3"
    
    def __init__(self, api_key: str = "", api_secret: str = ""):
        super().__init__("binance", api_key, api_secret)
    
    def is_configured(self) -> bool:
        """Binance public endpoints don't require API key."""
        return True
    
    async def get_quote(self, symbol: str) -> Optional[MarketData]:
        """Get current quote from Binance."""
        try:
            session = await self._get_session()
            
            binance_symbol = symbol.replace("/", "").replace("-", "").upper()
            
            url = f"{self.BASE_URL}/ticker/24hr"
            params = {"symbol": binance_symbol}
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    return MarketData(
                        symbol=symbol,
                        timestamp=datetime.utcnow(),
                        bid=float(data.get("bidPrice", 0)) if data.get("bidPrice") else None,
                        ask=float(data.get("askPrice", 0)) if data.get("askPrice") else None,
                        last=float(data.get("lastPrice", 0)) if data.get("lastPrice") else None,
                        open=float(data.get("openPrice", 0)) if data.get("openPrice") else None,
                        high=float(data.get("highPrice", 0)) if data.get("highPrice") else None,
                        low=float(data.get("lowPrice", 0)) if data.get("lowPrice") else None,
                        close=float(data.get("prevClosePrice", 0)) if data.get("prevClosePrice") else None,
                        volume=float(data.get("volume", 0)) if data.get("volume") else None,
                        vwap=float(data.get("weightedAvgPrice", 0)) if data.get("weightedAvgPrice") else None,
                        source="binance",
                        raw_data=data,
                    )
                elif response.status == 429:
                    logger.warning("Binance rate limit exceeded")
                    return None
                else:
                    logger.error(f"Binance request failed: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Binance error: {e}")
            return None
    
    async def get_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str,
    ) -> List[MarketData]:
        """Get historical data from Binance."""
        try:
            session = await self._get_session()
            
            binance_symbol = symbol.replace("/", "").replace("-", "").upper()
            
            interval_map = {
                "1m": "1m",
                "3m": "3m",
                "5m": "5m",
                "15m": "15m",
                "30m": "30m",
                "1h": "1h",
                "2h": "2h",
                "4h": "4h",
                "6h": "6h",
                "8h": "8h",
                "12h": "12h",
                "1d": "1d",
                "3d": "3d",
                "1w": "1w",
                "1M": "1M",
            }
            
            url = f"{self.BASE_URL}/klines"
            params = {
                "symbol": binance_symbol,
                "interval": interval_map.get(interval, "1m"),
                "startTime": int(start.timestamp() * 1000),
                "endTime": int(end.timestamp() * 1000),
                "limit": 1000,
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    result = []
                    
                    for kline in data:
                        try:
                            result.append(MarketData(
                                symbol=symbol,
                                timestamp=datetime.fromtimestamp(kline[0] / 1000),
                                open=float(kline[1]),
                                high=float(kline[2]),
                                low=float(kline[3]),
                                close=float(kline[4]),
                                volume=float(kline[5]),
                                source="binance",
                            ))
                        except (ValueError, IndexError) as e:
                            logger.warning(f"Failed to parse Binance kline: {e}")
                    
                    return result
                else:
                    logger.error(f"Binance historical request failed: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Binance historical error: {e}")
            return []


class CoinbaseAdapter(ProviderAdapter):
    """Adapter for Coinbase API."""
    
    BASE_URL = "https://api.exchange.coinbase.com"
    
    def __init__(self, api_key: str = "", api_secret: str = ""):
        super().__init__("coinbase", api_key, api_secret)
    
    def is_configured(self) -> bool:
        """Coinbase public endpoints don't require API key."""
        return True
    
    async def get_quote(self, symbol: str) -> Optional[MarketData]:
        """Get current quote from Coinbase."""
        try:
            session = await self._get_session()
            
            coinbase_symbol = symbol.replace("/", "-").upper()
            
            url = f"{self.BASE_URL}/products/{coinbase_symbol}/ticker"
            
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    return MarketData(
                        symbol=symbol,
                        timestamp=datetime.utcnow(),
                        bid=float(data.get("bid", 0)) if data.get("bid") else None,
                        ask=float(data.get("ask", 0)) if data.get("ask") else None,
                        last=float(data.get("price", 0)) if data.get("price") else None,
                        volume=float(data.get("volume", 0)) if data.get("volume") else None,
                        source="coinbase",
                        raw_data=data,
                    )
                elif response.status == 429:
                    logger.warning("Coinbase rate limit exceeded")
                    return None
                else:
                    return None
                    
        except Exception as e:
            logger.error(f"Coinbase error: {e}")
            return None
    
    async def get_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str,
    ) -> List[MarketData]:
        """Get historical data from Coinbase."""
        try:
            session = await self._get_session()
            
            coinbase_symbol = symbol.replace("/", "-").upper()
            
            granularity_map = {
                "1m": 60,
                "5m": 300,
                "15m": 900,
                "1h": 3600,
                "6h": 21600,
                "1d": 86400,
            }
            
            url = f"{self.BASE_URL}/products/{coinbase_symbol}/candles"
            params = {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "granularity": granularity_map.get(interval, 60),
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    result = []
                    
                    for candle in data:
                        try:
                            result.append(MarketData(
                                symbol=symbol,
                                timestamp=datetime.fromtimestamp(candle[0]),
                                low=float(candle[1]),
                                high=float(candle[2]),
                                open=float(candle[3]),
                                close=float(candle[4]),
                                volume=float(candle[5]),
                                source="coinbase",
                            ))
                        except (ValueError, IndexError) as e:
                            logger.warning(f"Failed to parse Coinbase candle: {e}")
                    
                    result.sort(key=lambda x: x.timestamp)
                    return result
                else:
                    logger.error(f"Coinbase historical request failed: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Coinbase historical error: {e}")
            return []


class KrakenAdapter(ProviderAdapter):
    """Adapter for Kraken API."""
    
    BASE_URL = "https://api.kraken.com/0/public"
    
    def __init__(self, api_key: str = "", api_secret: str = ""):
        super().__init__("kraken", api_key, api_secret)
    
    def is_configured(self) -> bool:
        """Kraken public endpoints don't require API key."""
        return True
    
    async def get_quote(self, symbol: str) -> Optional[MarketData]:
        """Get current quote from Kraken."""
        try:
            session = await self._get_session()
            
            kraken_symbol = symbol.replace("/", "").replace("-", "").upper()
            
            url = f"{self.BASE_URL}/Ticker"
            params = {"pair": kraken_symbol}
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get("error"):
                        logger.warning(f"Kraken error: {data['error']}")
                        return None
                    
                    result = data.get("result", {})
                    if not result:
                        return None
                    
                    ticker = list(result.values())[0]
                    
                    return MarketData(
                        symbol=symbol,
                        timestamp=datetime.utcnow(),
                        bid=float(ticker["b"][0]) if ticker.get("b") else None,
                        ask=float(ticker["a"][0]) if ticker.get("a") else None,
                        last=float(ticker["c"][0]) if ticker.get("c") else None,
                        open=float(ticker["o"]) if ticker.get("o") else None,
                        high=float(ticker["h"][1]) if ticker.get("h") else None,
                        low=float(ticker["l"][1]) if ticker.get("l") else None,
                        volume=float(ticker["v"][1]) if ticker.get("v") else None,
                        vwap=float(ticker["p"][1]) if ticker.get("p") else None,
                        source="kraken",
                        raw_data=ticker,
                    )
                else:
                    logger.error(f"Kraken request failed: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Kraken error: {e}")
            return None
    
    async def get_historical(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str,
    ) -> List[MarketData]:
        """Get historical data from Kraken."""
        try:
            session = await self._get_session()
            
            kraken_symbol = symbol.replace("/", "").replace("-", "").upper()
            
            interval_map = {
                "1m": 1,
                "5m": 5,
                "15m": 15,
                "30m": 30,
                "1h": 60,
                "4h": 240,
                "1d": 1440,
                "1w": 10080,
            }
            
            url = f"{self.BASE_URL}/OHLC"
            params = {
                "pair": kraken_symbol,
                "interval": interval_map.get(interval, 1),
                "since": int(start.timestamp()),
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get("error"):
                        logger.warning(f"Kraken error: {data['error']}")
                        return []
                    
                    result_data = data.get("result", {})
                    ohlc_key = [k for k in result_data.keys() if k != "last"]
                    
                    if not ohlc_key:
                        return []
                    
                    ohlc = result_data[ohlc_key[0]]
                    result = []
                    
                    for candle in ohlc:
                        try:
                            timestamp = datetime.fromtimestamp(candle[0])
                            if start <= timestamp <= end:
                                result.append(MarketData(
                                    symbol=symbol,
                                    timestamp=timestamp,
                                    open=float(candle[1]),
                                    high=float(candle[2]),
                                    low=float(candle[3]),
                                    close=float(candle[4]),
                                    vwap=float(candle[5]),
                                    volume=float(candle[6]),
                                    source="kraken",
                                ))
                        except (ValueError, IndexError) as e:
                            logger.warning(f"Failed to parse Kraken candle: {e}")
                    
                    return result
                else:
                    logger.error(f"Kraken historical request failed: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Kraken historical error: {e}")
            return []


class ThirdPartyConnector(BaseConnector):
    """
    Unified connector for multiple third-party data providers.
    
    Features:
    - Simultaneous data collection from all configured APIs
    - Automatic failover between providers
    - Data aggregation and fusion
    - Rate limiting per provider
    - Caching with provider-specific TTLs
    - Data validation
    """
    
    def __init__(self, config: Optional[ThirdPartyConfig] = None):
        self.config = config or ThirdPartyConfig()
        
        super().__init__(
            name="third_party",
            auto_reconnect=self.config.auto_reconnect,
            reconnect_delay=self.config.reconnect_delay,
            max_reconnect_attempts=self.config.max_reconnect_attempts,
            heartbeat_interval=self.config.heartbeat_interval,
        )
        
        self._adapters: Dict[str, ProviderAdapter] = {}
        self._setup_adapters()
        
        if self.config.use_rate_limiter:
            self._rate_limiter = MultiProviderRateLimiter()
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
        
        logger.info(f"ThirdPartyConnector initialized with providers: {list(self._adapters.keys())}")
    
    def _setup_adapters(self) -> None:
        """Setup provider adapters based on configuration."""
        if "twelvedata" in self.config.providers:
            self._adapters["twelvedata"] = TwelveDataAdapter(
                api_key=self.config.twelvedata_api_key
            )
        
        if "alphavantage" in self.config.providers:
            self._adapters["alphavantage"] = AlphaVantageAdapter(
                api_key=self.config.alphavantage_api_key
            )
        
        if "binance" in self.config.providers:
            self._adapters["binance"] = BinanceAdapter(
                api_key=self.config.binance_api_key,
                api_secret=self.config.binance_api_secret,
            )
        
        if "coinbase" in self.config.providers:
            self._adapters["coinbase"] = CoinbaseAdapter(
                api_key=self.config.coinbase_api_key,
                api_secret=self.config.coinbase_api_secret,
            )
        
        if "kraken" in self.config.providers:
            self._adapters["kraken"] = KrakenAdapter(
                api_key=self.config.kraken_api_key,
                api_secret=self.config.kraken_api_secret,
            )
    
    def get_configured_providers(self) -> List[str]:
        """Get list of properly configured providers."""
        return [
            name for name, adapter in self._adapters.items()
            if adapter.is_configured()
        ]
    
    async def connect(self) -> bool:
        """Connect to all configured providers."""
        self.status = ConnectionStatus.CONNECTING
        
        configured = self.get_configured_providers()
        if not configured:
            logger.warning("No providers configured")
            self.status = ConnectionStatus.ERROR
            return False
        
        self.status = ConnectionStatus.CONNECTED
        self._emit_event(
            EventType.CONNECTED,
            metadata={"providers": configured}
        )
        
        logger.info(f"Connected to providers: {configured}")
        return True
    
    async def disconnect(self) -> None:
        """Disconnect from all providers."""
        for adapter in self._adapters.values():
            await adapter.close()
        
        self.status = ConnectionStatus.DISCONNECTED
        self._emit_event(EventType.DISCONNECTED)
        logger.info("Disconnected from all providers")
    
    async def subscribe(self, symbol: str) -> bool:
        """Subscribe to market data for a symbol."""
        with self._lock:
            self._subscriptions.add(symbol)
        
        self._emit_event(
            EventType.SUBSCRIPTION_ADDED,
            data={"symbol": symbol}
        )
        
        return True
    
    async def unsubscribe(self, symbol: str) -> bool:
        """Unsubscribe from market data for a symbol."""
        with self._lock:
            self._subscriptions.discard(symbol)
        
        self._emit_event(
            EventType.SUBSCRIPTION_REMOVED,
            data={"symbol": symbol}
        )
        
        return True
    
    async def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """
        Get current market data from all providers simultaneously.
        
        Collects data from all configured providers in parallel
        and returns the most complete/recent data.
        """
        if self._cache:
            cached = self._cache.get_symbol_data(symbol, "aggregated")
            if cached:
                self._emit_event(EventType.CACHE_HIT, metadata={"symbol": symbol})
                return cached
        
        if self.config.simultaneous_collection:
            return await self._get_market_data_simultaneous(symbol)
        else:
            return await self._get_market_data_fallback(symbol)
    
    async def _get_market_data_simultaneous(self, symbol: str) -> Optional[MarketData]:
        """Collect data from all providers simultaneously."""
        tasks = []
        provider_names = []
        
        for name, adapter in self._adapters.items():
            if not adapter.is_configured():
                continue
            
            if self._rate_limiter:
                acquired, _ = await self._rate_limiter.acquire(name, "quote")
                if not acquired:
                    logger.debug(f"Rate limited: {name}")
                    continue
            
            tasks.append(adapter.get_quote(symbol))
            provider_names.append(name)
        
        if not tasks:
            return None
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results: List[MarketData] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Provider {provider_names[i]} error: {result}")
                continue
            if result is not None:
                if self._rate_limiter:
                    self._rate_limiter.report_success(provider_names[i], "quote")
                valid_results.append(result)
        
        if not valid_results:
            return None
        
        aggregated = self._aggregate_market_data(valid_results)
        
        if self._validator:
            validation = self._validator.validate(aggregated)
            if not validation.is_valid:
                self._emit_event(
                    EventType.VALIDATION_FAILED,
                    data=validation,
                    metadata={"symbol": symbol}
                )
        
        if self._cache:
            self._cache.set_symbol_data(symbol, aggregated, "aggregated")
        
        self._emit_event(
            EventType.DATA_RECEIVED,
            data=aggregated,
            metadata={
                "symbol": symbol,
                "providers": [r.source for r in valid_results],
            }
        )
        
        return aggregated
    
    async def _get_market_data_fallback(self, symbol: str) -> Optional[MarketData]:
        """Get data from providers with fallback."""
        for name, adapter in self._adapters.items():
            if not adapter.is_configured():
                continue
            
            if self._rate_limiter:
                acquired = await self._rate_limiter.wait_and_acquire(name, "quote", max_wait=5.0)
                if not acquired:
                    continue
            
            result = await adapter.get_quote(symbol)
            if result is not None:
                if self._rate_limiter:
                    self._rate_limiter.report_success(name, "quote")
                
                if self._cache:
                    self._cache.set_symbol_data(symbol, result, name)
                
                return result
        
        return None
    
    def _aggregate_market_data(self, results: List[MarketData]) -> MarketData:
        """
        Aggregate market data from multiple sources.
        
        Uses the most recent timestamp and fills in missing fields
        from other sources.
        """
        if len(results) == 1:
            return results[0]
        
        results.sort(key=lambda x: x.timestamp, reverse=True)
        base = results[0]
        
        aggregated = MarketData(
            symbol=base.symbol,
            timestamp=base.timestamp,
            bid=base.bid,
            ask=base.ask,
            last=base.last,
            volume=base.volume,
            open=base.open,
            high=base.high,
            low=base.low,
            close=base.close,
            vwap=base.vwap,
            source="aggregated",
            raw_data={"sources": [r.source for r in results]},
        )
        
        for result in results[1:]:
            if aggregated.bid is None and result.bid is not None:
                aggregated.bid = result.bid
            if aggregated.ask is None and result.ask is not None:
                aggregated.ask = result.ask
            if aggregated.last is None and result.last is not None:
                aggregated.last = result.last
            if aggregated.volume is None and result.volume is not None:
                aggregated.volume = result.volume
            if aggregated.open is None and result.open is not None:
                aggregated.open = result.open
            if aggregated.high is None and result.high is not None:
                aggregated.high = result.high
            if aggregated.low is None and result.low is not None:
                aggregated.low = result.low
            if aggregated.close is None and result.close is not None:
                aggregated.close = result.close
            if aggregated.vwap is None and result.vwap is not None:
                aggregated.vwap = result.vwap
        
        return aggregated
    
    async def get_historical_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1m",
    ) -> List[MarketData]:
        """
        Get historical data from all providers simultaneously.
        
        Collects data from all configured providers and merges
        the results for the most complete dataset.
        """
        if self._cache:
            cached = self._cache.get_historical_data(symbol, start, end, interval, "aggregated")
            if cached:
                self._emit_event(EventType.CACHE_HIT, metadata={"symbol": symbol, "type": "historical"})
                return cached
        
        tasks = []
        provider_names = []
        
        for name, adapter in self._adapters.items():
            if not adapter.is_configured():
                continue
            
            if self._rate_limiter:
                acquired, _ = await self._rate_limiter.acquire(name, "historical")
                if not acquired:
                    continue
            
            tasks.append(adapter.get_historical(symbol, start, end, interval))
            provider_names.append(name)
        
        if not tasks:
            return []
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_data: Dict[datetime, MarketData] = {}
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Provider {provider_names[i]} historical error: {result}")
                continue
            
            if result:
                if self._rate_limiter:
                    self._rate_limiter.report_success(provider_names[i], "historical")
                
                for data in result:
                    ts = data.timestamp
                    if ts not in all_data:
                        all_data[ts] = data
                    else:
                        existing = all_data[ts]
                        if existing.volume is None and data.volume is not None:
                            existing.volume = data.volume
        
        merged = sorted(all_data.values(), key=lambda x: x.timestamp)
        
        if self._cache and merged:
            self._cache.set_historical_data(symbol, start, end, interval, merged, "aggregated")
        
        self._emit_event(
            EventType.DATA_RECEIVED,
            data={"symbol": symbol, "count": len(merged), "type": "historical"},
            metadata={"providers": provider_names}
        )
        
        return merged
    
    async def get_provider_data(
        self,
        provider: str,
        symbol: str,
    ) -> Optional[MarketData]:
        """Get data from a specific provider."""
        adapter = self._adapters.get(provider)
        if not adapter or not adapter.is_configured():
            return None
        
        if self._rate_limiter:
            acquired = await self._rate_limiter.wait_and_acquire(provider, "quote")
            if not acquired:
                return None
        
        result = await adapter.get_quote(symbol)
        
        if result and self._rate_limiter:
            self._rate_limiter.report_success(provider, "quote")
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connector statistics."""
        stats = super().get_stats()
        
        stats.update({
            "providers": list(self._adapters.keys()),
            "configured_providers": self.get_configured_providers(),
            "simultaneous_collection": self.config.simultaneous_collection,
        })
        
        if self._rate_limiter:
            stats["rate_limiters"] = self._rate_limiter.get_all_stats()
        
        if self._cache:
            stats["cache"] = self._cache.get_stats()
        
        return stats


def create_third_party_connector(
    providers: Optional[List[str]] = None,
    simultaneous: bool = True,
    **kwargs,
) -> ThirdPartyConnector:
    """
    Factory function to create a third-party connector.
    
    Args:
        providers: List of provider names to enable
        simultaneous: Whether to collect data from all providers simultaneously
        **kwargs: Additional ThirdPartyConfig parameters
        
    Returns:
        Configured ThirdPartyConnector instance
    """
    config = ThirdPartyConfig(
        providers=providers or ["twelvedata", "alphavantage", "binance", "coinbase", "kraken"],
        simultaneous_collection=simultaneous,
        **kwargs,
    )
    return ThirdPartyConnector(config)
