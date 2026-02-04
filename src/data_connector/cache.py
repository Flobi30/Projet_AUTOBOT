"""
Local Cache for Data Connector.

Implements multi-level caching with TTL, LRU eviction, and persistence.
"""

import asyncio
import hashlib
import json
import logging
import os
import pickle
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar, Union
from pathlib import Path

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CacheConfig:
    """Configuration for data cache."""
    max_size: int = 10000
    default_ttl: float = 300.0
    persist_to_disk: bool = True
    persist_path: str = "cache"
    persist_interval: float = 60.0
    compression: bool = False
    memory_limit_mb: float = 512.0
    cleanup_interval: float = 30.0
    
    symbol_ttl: float = 60.0
    historical_ttl: float = 3600.0
    metadata_ttl: float = 86400.0


@dataclass
class CacheEntry(Generic[T]):
    """A single cache entry with metadata."""
    key: str
    value: T
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    size_bytes: int = 0
    tags: List[str] = field(default_factory=list)
    
    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.expires_at <= 0:
            return False
        return time.time() > self.expires_at
    
    @property
    def age(self) -> float:
        """Get age of entry in seconds."""
        return time.time() - self.created_at
    
    @property
    def ttl_remaining(self) -> float:
        """Get remaining TTL in seconds."""
        if self.expires_at <= 0:
            return float("inf")
        return max(0, self.expires_at - time.time())


class DataCache:
    """
    Multi-level cache with TTL and LRU eviction.
    
    Features:
    - In-memory LRU cache
    - Optional disk persistence
    - Per-key TTL
    - Tag-based invalidation
    - Memory limit enforcement
    - Async-safe operations
    """
    
    def __init__(self, config: Optional[CacheConfig] = None, name: str = "default"):
        self.config = config or CacheConfig()
        self.name = name
        
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._async_lock = asyncio.Lock()
        
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._current_size_bytes = 0
        
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._persist_task: Optional[asyncio.Task] = None
        
        if self.config.persist_to_disk:
            self._persist_path = Path(self.config.persist_path)
            self._persist_path.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()
        
        logger.info(f"DataCache '{name}' initialized: max_size={self.config.max_size}")
    
    def _estimate_size(self, value: Any) -> int:
        """Estimate memory size of a value in bytes."""
        try:
            return len(pickle.dumps(value))
        except Exception:
            return 1024
    
    def _generate_key(self, *args, **kwargs) -> str:
        """Generate a cache key from arguments."""
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]
    
    def _evict_if_needed(self) -> None:
        """Evict entries if cache is over limits."""
        while len(self._cache) >= self.config.max_size:
            self._cache.popitem(last=False)
            self._evictions += 1
        
        memory_limit_bytes = self.config.memory_limit_mb * 1024 * 1024
        while self._current_size_bytes > memory_limit_bytes and self._cache:
            key, entry = self._cache.popitem(last=False)
            self._current_size_bytes -= entry.size_bytes
            self._evictions += 1
    
    def _cleanup_expired(self) -> int:
        """Remove expired entries. Returns count of removed entries."""
        removed = 0
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired
            ]
            for key in expired_keys:
                entry = self._cache.pop(key)
                self._current_size_bytes -= entry.size_bytes
                removed += 1
        
        if removed > 0:
            logger.debug(f"DataCache '{self.name}': Cleaned up {removed} expired entries")
        
        return removed
    
    def get(self, key: str, default: T = None) -> Optional[T]:
        """
        Get a value from cache.
        
        Args:
            key: Cache key
            default: Default value if not found
            
        Returns:
            Cached value or default
        """
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._misses += 1
                return default
            
            if entry.is_expired:
                self._cache.pop(key)
                self._current_size_bytes -= entry.size_bytes
                self._misses += 1
                return default
            
            self._cache.move_to_end(key)
            entry.access_count += 1
            entry.last_accessed = time.time()
            self._hits += 1
            
            return entry.value
    
    async def get_async(self, key: str, default: T = None) -> Optional[T]:
        """Async version of get."""
        async with self._async_lock:
            return self.get(key, default)
    
    def set(
        self,
        key: str,
        value: T,
        ttl: Optional[float] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """
        Set a value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None for default)
            tags: Optional tags for group invalidation
        """
        with self._lock:
            if key in self._cache:
                old_entry = self._cache.pop(key)
                self._current_size_bytes -= old_entry.size_bytes
            
            self._evict_if_needed()
            
            size_bytes = self._estimate_size(value)
            ttl = ttl if ttl is not None else self.config.default_ttl
            
            entry = CacheEntry(
                key=key,
                value=value,
                expires_at=time.time() + ttl if ttl > 0 else 0,
                size_bytes=size_bytes,
                tags=tags or [],
            )
            
            self._cache[key] = entry
            self._current_size_bytes += size_bytes
    
    async def set_async(
        self,
        key: str,
        value: T,
        ttl: Optional[float] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Async version of set."""
        async with self._async_lock:
            self.set(key, value, ttl, tags)
    
    def delete(self, key: str) -> bool:
        """
        Delete a key from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key was deleted
        """
        with self._lock:
            if key in self._cache:
                entry = self._cache.pop(key)
                self._current_size_bytes -= entry.size_bytes
                return True
            return False
    
    async def delete_async(self, key: str) -> bool:
        """Async version of delete."""
        async with self._async_lock:
            return self.delete(key)
    
    def invalidate_by_tag(self, tag: str) -> int:
        """
        Invalidate all entries with a specific tag.
        
        Args:
            tag: Tag to invalidate
            
        Returns:
            Number of entries invalidated
        """
        with self._lock:
            keys_to_remove = [
                key for key, entry in self._cache.items()
                if tag in entry.tags
            ]
            
            for key in keys_to_remove:
                entry = self._cache.pop(key)
                self._current_size_bytes -= entry.size_bytes
            
            return len(keys_to_remove)
    
    def invalidate_by_prefix(self, prefix: str) -> int:
        """
        Invalidate all entries with keys starting with prefix.
        
        Args:
            prefix: Key prefix to invalidate
            
        Returns:
            Number of entries invalidated
        """
        with self._lock:
            keys_to_remove = [
                key for key in self._cache.keys()
                if key.startswith(prefix)
            ]
            
            for key in keys_to_remove:
                entry = self._cache.pop(key)
                self._current_size_bytes -= entry.size_bytes
            
            return len(keys_to_remove)
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._current_size_bytes = 0
            logger.info(f"DataCache '{self.name}': Cleared all entries")
    
    def get_or_set(
        self,
        key: str,
        factory: Callable[[], T],
        ttl: Optional[float] = None,
        tags: Optional[List[str]] = None,
    ) -> T:
        """
        Get value from cache or compute and store it.
        
        Args:
            key: Cache key
            factory: Function to compute value if not cached
            ttl: Time-to-live in seconds
            tags: Optional tags
            
        Returns:
            Cached or computed value
        """
        value = self.get(key)
        if value is not None:
            return value
        
        value = factory()
        self.set(key, value, ttl, tags)
        return value
    
    async def get_or_set_async(
        self,
        key: str,
        factory: Callable[[], T],
        ttl: Optional[float] = None,
        tags: Optional[List[str]] = None,
    ) -> T:
        """Async version of get_or_set."""
        value = await self.get_async(key)
        if value is not None:
            return value
        
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()
        
        await self.set_async(key, value, ttl, tags)
        return value
    
    def _save_to_disk(self) -> None:
        """Persist cache to disk."""
        if not self.config.persist_to_disk:
            return
        
        try:
            cache_file = self._persist_path / f"{self.name}.cache"
            
            with self._lock:
                data = {
                    key: {
                        "value": entry.value,
                        "expires_at": entry.expires_at,
                        "tags": entry.tags,
                    }
                    for key, entry in self._cache.items()
                    if not entry.is_expired
                }
            
            with open(cache_file, "wb") as f:
                pickle.dump(data, f)
            
            logger.debug(f"DataCache '{self.name}': Persisted {len(data)} entries to disk")
            
        except Exception as e:
            logger.error(f"DataCache '{self.name}': Failed to persist to disk: {e}")
    
    def _load_from_disk(self) -> None:
        """Load cache from disk."""
        if not self.config.persist_to_disk:
            return
        
        try:
            cache_file = self._persist_path / f"{self.name}.cache"
            
            if not cache_file.exists():
                return
            
            with open(cache_file, "rb") as f:
                data = pickle.load(f)
            
            loaded = 0
            for key, entry_data in data.items():
                if entry_data["expires_at"] > 0 and entry_data["expires_at"] < time.time():
                    continue
                
                self.set(
                    key,
                    entry_data["value"],
                    ttl=max(0, entry_data["expires_at"] - time.time()) if entry_data["expires_at"] > 0 else 0,
                    tags=entry_data.get("tags", []),
                )
                loaded += 1
            
            logger.info(f"DataCache '{self.name}': Loaded {loaded} entries from disk")
            
        except Exception as e:
            logger.error(f"DataCache '{self.name}': Failed to load from disk: {e}")
    
    async def _cleanup_loop(self) -> None:
        """Background cleanup loop."""
        while self._running:
            try:
                self._cleanup_expired()
            except Exception as e:
                logger.error(f"DataCache '{self.name}': Cleanup error: {e}")
            
            await asyncio.sleep(self.config.cleanup_interval)
    
    async def _persist_loop(self) -> None:
        """Background persistence loop."""
        while self._running:
            try:
                self._save_to_disk()
            except Exception as e:
                logger.error(f"DataCache '{self.name}': Persist error: {e}")
            
            await asyncio.sleep(self.config.persist_interval)
    
    async def start(self) -> None:
        """Start background tasks."""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        if self.config.persist_to_disk:
            self._persist_task = asyncio.create_task(self._persist_loop())
        
        logger.info(f"DataCache '{self.name}': Started background tasks")
    
    async def stop(self) -> None:
        """Stop background tasks and persist."""
        self._running = False
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        if self._persist_task:
            self._persist_task.cancel()
            try:
                await self._persist_task
            except asyncio.CancelledError:
                pass
        
        self._save_to_disk()
        logger.info(f"DataCache '{self.name}': Stopped")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0.0
            
            return {
                "name": self.name,
                "entries": len(self._cache),
                "max_size": self.config.max_size,
                "size_bytes": self._current_size_bytes,
                "size_mb": self._current_size_bytes / (1024 * 1024),
                "memory_limit_mb": self.config.memory_limit_mb,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "evictions": self._evictions,
                "default_ttl": self.config.default_ttl,
            }


class MarketDataCache(DataCache):
    """
    Specialized cache for market data.
    
    Provides convenience methods for caching market data
    with appropriate TTLs and key generation.
    """
    
    def __init__(self, config: Optional[CacheConfig] = None):
        super().__init__(config or CacheConfig(), name="market_data")
    
    def _symbol_key(self, symbol: str, source: str = "") -> str:
        """Generate key for symbol data."""
        return f"symbol:{source}:{symbol}"
    
    def _historical_key(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str,
        source: str = "",
    ) -> str:
        """Generate key for historical data."""
        return f"historical:{source}:{symbol}:{interval}:{start.isoformat()}:{end.isoformat()}"
    
    def get_symbol_data(self, symbol: str, source: str = "") -> Optional[Any]:
        """Get cached symbol data."""
        return self.get(self._symbol_key(symbol, source))
    
    def set_symbol_data(
        self,
        symbol: str,
        data: Any,
        source: str = "",
        ttl: Optional[float] = None,
    ) -> None:
        """Cache symbol data."""
        self.set(
            self._symbol_key(symbol, source),
            data,
            ttl=ttl or self.config.symbol_ttl,
            tags=[f"symbol:{symbol}", f"source:{source}"],
        )
    
    def get_historical_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str,
        source: str = "",
    ) -> Optional[Any]:
        """Get cached historical data."""
        return self.get(self._historical_key(symbol, start, end, interval, source))
    
    def set_historical_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str,
        data: Any,
        source: str = "",
        ttl: Optional[float] = None,
    ) -> None:
        """Cache historical data."""
        self.set(
            self._historical_key(symbol, start, end, interval, source),
            data,
            ttl=ttl or self.config.historical_ttl,
            tags=[f"symbol:{symbol}", f"source:{source}", "historical"],
        )
    
    def invalidate_symbol(self, symbol: str) -> int:
        """Invalidate all cached data for a symbol."""
        return self.invalidate_by_tag(f"symbol:{symbol}")
    
    def invalidate_source(self, source: str) -> int:
        """Invalidate all cached data from a source."""
        return self.invalidate_by_tag(f"source:{source}")
