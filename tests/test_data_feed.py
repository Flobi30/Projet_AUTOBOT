import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from src.autobot.services.data_feed.cache import RedisCache
from src.autobot.services.data_feed.connections import WebSocketManager
from src.autobot.services.data_feed.config import DataFeedConfig

class TestRedisCache:
    @pytest.fixture
    async def redis_cache(self):
        cache = RedisCache("redis://localhost:6379")
        cache.redis = AsyncMock()
        return cache
    
    @pytest.mark.asyncio
    async def test_connect(self):
        cache = RedisCache("redis://localhost:6379")
        
        with patch('aioredis.from_url') as mock_from_url:
            mock_redis = AsyncMock()
            mock_from_url.return_value = mock_redis
            
            await cache.connect()
            
            assert cache.redis == mock_redis
            mock_redis.ping.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_store_tick(self, redis_cache):
        symbol = "BTC/USDT"
        tick_data = {
            "last": 50000.0,
            "bid": 49999.0,
            "ask": 50001.0,
            "baseVolume": 1000.0,
            "exchange": "binance"
        }
        
        mock_pipeline = AsyncMock()
        redis_cache.redis.pipeline.return_value = mock_pipeline
        
        await redis_cache.store_tick(symbol, tick_data)
        
        redis_cache.redis.pipeline.assert_called_once()
        mock_pipeline.lpush.assert_called_once()
        mock_pipeline.ltrim.assert_called_once()
        mock_pipeline.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_latest_ticks(self, redis_cache):
        symbol = "BTC/USDT"
        mock_tick_data = [
            json.dumps({"timestamp": "2023-01-01T00:00:00", "price": 50000.0}),
            json.dumps({"timestamp": "2023-01-01T00:01:00", "price": 50100.0})
        ]
        
        redis_cache.redis.lrange.return_value = mock_tick_data
        
        ticks = await redis_cache.get_latest_ticks(symbol, 2)
        
        assert len(ticks) == 2
        assert ticks[0]["price"] == 50000.0
        assert ticks[1]["price"] == 50100.0
        redis_cache.redis.lrange.assert_called_once_with("ticks:BTC/USDT", 0, 1)
    
    @pytest.mark.asyncio
    async def test_health_check(self, redis_cache):
        redis_cache.redis.keys.return_value = ["ticks:BTC/USDT", "ticks:ETH/USDT"]
        redis_cache.redis.llen.return_value = 100
        
        health = await redis_cache.health_check()
        
        assert health["status"] == "healthy"
        assert health["symbols_tracked"] == 2
        assert "BTC/USDT" in health["symbol_stats"]
        assert "ETH/USDT" in health["symbol_stats"]

class TestWebSocketManager:
    @pytest.fixture
    def websocket_manager(self):
        return WebSocketManager()
    
    @pytest.mark.asyncio
    async def test_initialize_exchanges(self, websocket_manager):
        with patch('ccxt.pro.binance') as mock_binance_class:
            mock_exchange = AsyncMock()
            mock_exchange.load_markets = AsyncMock()
            mock_binance_class.return_value = mock_exchange
            
            await websocket_manager.initialize_exchanges()
            
            assert "binance" in websocket_manager.exchanges
            mock_exchange.load_markets.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_check(self, websocket_manager):
        mock_exchange = MagicMock()
        mock_exchange.markets = {"BTC/USDT": {}, "ETH/USDT": {}}
        websocket_manager.exchanges = {"binance": mock_exchange}
        websocket_manager.running = True
        
        health = await websocket_manager.health_check()
        
        assert health["status"] == "healthy"
        assert health["running"] is True
        assert "binance" in health["exchanges"]
        assert health["exchanges"]["binance"]["status"] == "connected"

class TestDataFeedConfig:
    def test_default_config(self):
        assert DataFeedConfig.REDIS_URL == "redis://localhost:6379"
        assert "binance" in DataFeedConfig.SUPPORTED_EXCHANGES
        assert "kraken" in DataFeedConfig.SUPPORTED_EXCHANGES
        assert "coinbase" in DataFeedConfig.SUPPORTED_EXCHANGES
        assert DataFeedConfig.TICK_HISTORY_SIZE == 1000
        assert DataFeedConfig.HEALTH_CHECK_PORT == 8001

@pytest.mark.asyncio
async def test_integration_cache_and_websocket():
    cache = RedisCache()
    cache.redis = AsyncMock()
    
    websocket_manager = WebSocketManager(cache_callback=cache.store_tick)
    
    mock_pipeline = AsyncMock()
    cache.redis.pipeline.return_value = mock_pipeline
    
    tick_data = {
        "last": 50000.0,
        "bid": 49999.0,
        "ask": 50001.0,
        "exchange": "binance"
    }
    
    await websocket_manager.cache_callback("BTC/USDT", tick_data)
    
    cache.redis.pipeline.assert_called_once()
    mock_pipeline.lpush.assert_called_once()
    mock_pipeline.ltrim.assert_called_once()
    mock_pipeline.execute.assert_called_once()

if __name__ == "__main__":
    pytest.main([__file__])
