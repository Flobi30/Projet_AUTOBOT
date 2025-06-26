import os
from typing import List, Dict, Any

class DataFeedConfig:
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    SUPPORTED_EXCHANGES: List[str] = ["binance", "kraken", "coinbase"]
    
    DEFAULT_SYMBOLS: List[str] = ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
    SYMBOLS: List[str] = os.getenv("DATA_FEED_SYMBOLS", ",".join(DEFAULT_SYMBOLS)).split(",")
    
    TICK_HISTORY_SIZE: int = int(os.getenv("TICK_HISTORY_SIZE", "1000"))
    
    EXCHANGE_CONFIGS: Dict[str, Dict[str, Any]] = {
        "binance": {
            "api_key": os.getenv("BINANCE_API_KEY"),
            "api_secret": os.getenv("BINANCE_API_SECRET"),
            "sandbox": False,
            "timeout": 30000,
            "enableRateLimit": True,
        },
        "kraken": {
            "api_key": os.getenv("KRAKEN_API_KEY"),
            "api_secret": os.getenv("KRAKEN_API_SECRET"),
            "sandbox": False,
            "timeout": 30000,
            "enableRateLimit": True,
        },
        "coinbase": {
            "api_key": os.getenv("COINBASE_API_KEY"),
            "api_secret": os.getenv("COINBASE_API_SECRET"),
            "sandbox": False,
            "timeout": 30000,
            "enableRateLimit": True,
        }
    }
    
    WEBSOCKET_RECONNECT_DELAY: int = 5
    MAX_RECONNECT_ATTEMPTS: int = 10
    
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    HEALTH_CHECK_PORT: int = 8001
