"""Tests for Cache module."""

import asyncio
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import tempfile
import os

import sys
sys.path.insert(0, "/home/ubuntu/Projet_AUTOBOT/src")

from data_connector.cache import (
    CacheConfig,
    CacheEntry,
    DataCache,
    MarketDataCache,
)
from data_connector.base import MarketData


class TestCacheConfig:
    """Tests for CacheConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = CacheConfig()
        
        assert config.max_size == 10000
        assert config.default_ttl == 300.0
        assert config.persist_to_disk is True
        assert config.memory_limit_mb == 512.0
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = CacheConfig(
            max_size=1000,
            default_ttl=60.0,
            persist_to_disk=False,
        )
        
        assert config.max_size == 1000
        assert config.default_ttl == 60.0
        assert config.persist_to_disk is False
    
    def test_specialized_ttls(self):
        """Test specialized TTL values."""
        config = CacheConfig(
            symbol_ttl=30.0,
            historical_ttl=7200.0,
            metadata_ttl=43200.0,
        )
        
        assert config.symbol_ttl == 30.0
        assert config.historical_ttl == 7200.0
        assert config.metadata_ttl == 43200.0


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""
    
    def test_entry_creation(self):
        """Test basic entry creation."""
        entry = CacheEntry(
            key="test_key",
            value={"data": "test"},
        )
        
        assert entry.key == "test_key"
        assert entry.value == {"data": "test"}
        assert entry.access_count == 0
    
    def test_entry_not_expired(self):
        """Test entry that is not expired."""
        entry = CacheEntry(
            key="test",
            value="data",
            expires_at=time.time() + 3600,
        )
        
        assert entry.is_expired is False
    
    def test_entry_expired(self):
        """Test entry that is expired."""
        entry = CacheEntry(
            key="test",
            value="data",
            expires_at=time.time() - 1,
        )
        
        assert entry.is_expired is True
    
    def test_entry_no_expiry(self):
        """Test entry with no expiry."""
        entry = CacheEntry(
            key="test",
            value="data",
            expires_at=0,
        )
        
        assert entry.is_expired is False
    
    def test_entry_age(self):
        """Test entry age calculation."""
        entry = CacheEntry(
            key="test",
            value="data",
        )
        
        time.sleep(0.1)
        
        assert entry.age >= 0.1
    
    def test_entry_ttl_remaining(self):
        """Test TTL remaining calculation."""
        entry = CacheEntry(
            key="test",
            value="data",
            expires_at=time.time() + 60,
        )
        
        assert 59 <= entry.ttl_remaining <= 60
    
    def test_entry_ttl_remaining_no_expiry(self):
        """Test TTL remaining with no expiry."""
        entry = CacheEntry(
            key="test",
            value="data",
            expires_at=0,
        )
        
        assert entry.ttl_remaining == float("inf")


class TestDataCache:
    """Tests for DataCache class."""
    
    def test_cache_creation(self):
        """Test cache creation."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        assert cache.name == "test"
    
    def test_set_and_get(self):
        """Test basic set and get operations."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        cache.set("key1", "value1")
        
        result = cache.get("key1")
        assert result == "value1"
    
    def test_get_missing_key(self):
        """Test getting a missing key."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        result = cache.get("nonexistent")
        assert result is None
    
    def test_get_with_default(self):
        """Test getting with default value."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        result = cache.get("nonexistent", default="default_value")
        assert result == "default_value"
    
    def test_set_with_ttl(self):
        """Test setting with custom TTL."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        cache.set("key1", "value1", ttl=0.1)
        
        assert cache.get("key1") == "value1"
        
        time.sleep(0.15)
        
        assert cache.get("key1") is None
    
    def test_set_with_tags(self):
        """Test setting with tags."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        cache.set("key1", "value1", tags=["tag1", "tag2"])
        cache.set("key2", "value2", tags=["tag1"])
        cache.set("key3", "value3", tags=["tag2"])
        
        count = cache.invalidate_by_tag("tag1")
        
        assert count == 2
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") == "value3"
    
    def test_delete(self):
        """Test deleting a key."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        cache.set("key1", "value1")
        
        result = cache.delete("key1")
        
        assert result is True
        assert cache.get("key1") is None
    
    def test_delete_missing_key(self):
        """Test deleting a missing key."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        result = cache.delete("nonexistent")
        
        assert result is False
    
    def test_clear(self):
        """Test clearing the cache."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        cache.clear()
        
        assert cache.get("key1") is None
        assert cache.get("key2") is None
    
    def test_invalidate_by_prefix(self):
        """Test invalidating by prefix."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        cache.set("user:1", "data1")
        cache.set("user:2", "data2")
        cache.set("order:1", "data3")
        
        count = cache.invalidate_by_prefix("user:")
        
        assert count == 2
        assert cache.get("user:1") is None
        assert cache.get("user:2") is None
        assert cache.get("order:1") == "data3"
    
    def test_get_or_set(self):
        """Test get_or_set method."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        factory = MagicMock(return_value="computed_value")
        
        result1 = cache.get_or_set("key1", factory)
        result2 = cache.get_or_set("key1", factory)
        
        assert result1 == "computed_value"
        assert result2 == "computed_value"
        factory.assert_called_once()
    
    def test_lru_eviction(self):
        """Test LRU eviction when max_size is reached."""
        config = CacheConfig(max_size=3, persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        
        cache.get("key1")
        
        cache.set("key4", "value4")
        
        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"
    
    def test_get_stats(self):
        """Test getting cache statistics."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        cache.set("key1", "value1")
        cache.get("key1")
        cache.get("key1")
        cache.get("nonexistent")
        
        stats = cache.get_stats()
        
        assert stats["name"] == "test"
        assert stats["entries"] == 1
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 2/3
    
    @pytest.mark.asyncio
    async def test_get_async(self):
        """Test async get operation."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        cache.set("key1", "value1")
        
        result = await cache.get_async("key1")
        
        assert result == "value1"
    
    @pytest.mark.asyncio
    async def test_set_async(self):
        """Test async set operation."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        await cache.set_async("key1", "value1")
        
        result = cache.get("key1")
        assert result == "value1"
    
    @pytest.mark.asyncio
    async def test_delete_async(self):
        """Test async delete operation."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        cache.set("key1", "value1")
        
        result = await cache.delete_async("key1")
        
        assert result is True
        assert cache.get("key1") is None
    
    def test_update_existing_key(self):
        """Test updating an existing key."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        cache.set("key1", "value1")
        cache.set("key1", "value2")
        
        result = cache.get("key1")
        assert result == "value2"
    
    def test_complex_values(self):
        """Test caching complex values."""
        config = CacheConfig(persist_to_disk=False)
        cache = DataCache(config=config, name="test")
        
        complex_value = {
            "list": [1, 2, 3],
            "nested": {"a": 1, "b": 2},
            "tuple": (1, 2, 3),
        }
        
        cache.set("complex", complex_value)
        
        result = cache.get("complex")
        assert result == complex_value


class TestMarketDataCache:
    """Tests for MarketDataCache class."""
    
    def test_cache_creation(self):
        """Test MarketDataCache creation."""
        cache = MarketDataCache()
        
        assert cache.name == "market_data"
    
    def test_set_and_get_symbol_data(self):
        """Test setting and getting symbol data."""
        config = CacheConfig(persist_to_disk=False)
        cache = MarketDataCache(config=config)
        
        data = MarketData(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            last=150.0,
        )
        
        cache.set_symbol_data("AAPL", data, source="test")
        
        result = cache.get_symbol_data("AAPL", source="test")
        assert result == data
    
    def test_set_and_get_historical_data(self):
        """Test setting and getting historical data."""
        config = CacheConfig(persist_to_disk=False)
        cache = MarketDataCache(config=config)
        
        start = datetime.utcnow() - timedelta(days=1)
        end = datetime.utcnow()
        
        data = [
            MarketData(symbol="AAPL", timestamp=start, close=149.0),
            MarketData(symbol="AAPL", timestamp=end, close=150.0),
        ]
        
        cache.set_historical_data("AAPL", start, end, "1h", data, source="test")
        
        result = cache.get_historical_data("AAPL", start, end, "1h", source="test")
        assert result == data
    
    def test_invalidate_symbol(self):
        """Test invalidating all data for a symbol."""
        config = CacheConfig(persist_to_disk=False)
        cache = MarketDataCache(config=config)
        
        cache.set_symbol_data("AAPL", {"price": 150}, source="test1")
        cache.set_symbol_data("AAPL", {"price": 151}, source="test2")
        cache.set_symbol_data("GOOGL", {"price": 2800}, source="test1")
        
        count = cache.invalidate_symbol("AAPL")
        
        assert count == 2
        assert cache.get_symbol_data("AAPL", source="test1") is None
        assert cache.get_symbol_data("AAPL", source="test2") is None
        assert cache.get_symbol_data("GOOGL", source="test1") is not None
    
    def test_invalidate_source(self):
        """Test invalidating all data from a source."""
        config = CacheConfig(persist_to_disk=False)
        cache = MarketDataCache(config=config)
        
        cache.set_symbol_data("AAPL", {"price": 150}, source="binance")
        cache.set_symbol_data("GOOGL", {"price": 2800}, source="binance")
        cache.set_symbol_data("MSFT", {"price": 300}, source="coinbase")
        
        count = cache.invalidate_source("binance")
        
        assert count == 2
        assert cache.get_symbol_data("AAPL", source="binance") is None
        assert cache.get_symbol_data("GOOGL", source="binance") is None
        assert cache.get_symbol_data("MSFT", source="coinbase") is not None
    
    def test_symbol_ttl(self):
        """Test symbol-specific TTL."""
        config = CacheConfig(persist_to_disk=False, symbol_ttl=0.1)
        cache = MarketDataCache(config=config)
        
        cache.set_symbol_data("AAPL", {"price": 150}, source="test")
        
        assert cache.get_symbol_data("AAPL", source="test") is not None
        
        time.sleep(0.15)
        
        assert cache.get_symbol_data("AAPL", source="test") is None


class TestCachePersistence:
    """Tests for cache persistence."""
    
    def test_persist_and_load(self):
        """Test persisting and loading cache from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = CacheConfig(
                persist_to_disk=True,
                persist_path=tmpdir,
                default_ttl=3600,
            )
            
            cache1 = DataCache(config=config, name="persist_test")
            cache1.set("key1", "value1")
            cache1.set("key2", "value2")
            cache1._save_to_disk()
            
            cache2 = DataCache(config=config, name="persist_test")
            
            assert cache2.get("key1") == "value1"
            assert cache2.get("key2") == "value2"
    
    def test_persist_excludes_expired(self):
        """Test that expired entries are not persisted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = CacheConfig(
                persist_to_disk=True,
                persist_path=tmpdir,
                default_ttl=0.1,
            )
            
            cache1 = DataCache(config=config, name="persist_test")
            cache1.set("key1", "value1")
            
            time.sleep(0.15)
            
            cache1._save_to_disk()
            
            cache2 = DataCache(config=config, name="persist_test")
            
            assert cache2.get("key1") is None
