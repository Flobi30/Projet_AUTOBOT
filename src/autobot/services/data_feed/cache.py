import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import aioredis
from .config import DataFeedConfig

logger = logging.getLogger(__name__)

class RedisCache:
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or DataFeedConfig.REDIS_URL
        self.redis: Optional[aioredis.Redis] = None
        self.tick_history_size = DataFeedConfig.TICK_HISTORY_SIZE
        
    async def connect(self):
        try:
            self.redis = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={}
            )
            await self.redis.ping()
            logger.info(f"Connected to Redis at {self.redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def disconnect(self):
        if self.redis:
            await self.redis.close()
            logger.info("Disconnected from Redis")
    
    async def store_tick(self, symbol: str, tick_data: Dict[str, Any]):
        if not self.redis:
            logger.error("Redis connection not established")
            return
        
        try:
            key = f"ticks:{symbol}"
            
            tick_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "symbol": symbol,
                "price": tick_data.get("last", tick_data.get("price")),
                "bid": tick_data.get("bid"),
                "ask": tick_data.get("ask"),
                "volume": tick_data.get("baseVolume", tick_data.get("volume")),
                "exchange": tick_data.get("exchange"),
                "raw_data": tick_data
            }
            
            tick_json = json.dumps(tick_entry)
            
            pipe = self.redis.pipeline()
            pipe.lpush(key, tick_json)
            pipe.ltrim(key, 0, self.tick_history_size - 1)
            await pipe.execute()
            
            logger.debug(f"Stored tick for {symbol}: {tick_entry['price']}")
            
        except Exception as e:
            logger.error(f"Failed to store tick for {symbol}: {e}")
    
    async def get_latest_ticks(self, symbol: str, count: int = 10) -> List[Dict[str, Any]]:
        if not self.redis:
            logger.error("Redis connection not established")
            return []
        
        try:
            key = f"ticks:{symbol}"
            tick_data = await self.redis.lrange(key, 0, count - 1)
            
            ticks = []
            for tick_json in tick_data:
                try:
                    tick = json.loads(tick_json)
                    ticks.append(tick)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse tick data: {e}")
            
            return ticks
            
        except Exception as e:
            logger.error(f"Failed to get ticks for {symbol}: {e}")
            return []
    
    async def get_tick_count(self, symbol: str) -> int:
        if not self.redis:
            return 0
        
        try:
            key = f"ticks:{symbol}"
            return await self.redis.llen(key)
        except Exception as e:
            logger.error(f"Failed to get tick count for {symbol}: {e}")
            return 0
    
    async def get_all_symbols(self) -> List[str]:
        if not self.redis:
            return []
        
        try:
            keys = await self.redis.keys("ticks:*")
            symbols = [key.replace("ticks:", "") for key in keys]
            return symbols
        except Exception as e:
            logger.error(f"Failed to get symbols: {e}")
            return []
    
    async def health_check(self) -> Dict[str, Any]:
        try:
            if not self.redis:
                return {"status": "error", "message": "Redis connection not established"}
            
            await self.redis.ping()
            symbols = await self.get_all_symbols()
            
            symbol_stats = {}
            for symbol in symbols:
                count = await self.get_tick_count(symbol)
                symbol_stats[symbol] = count
            
            return {
                "status": "healthy",
                "redis_url": self.redis_url,
                "symbols_tracked": len(symbols),
                "symbol_stats": symbol_stats
            }
            
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {"status": "error", "message": str(e)}
