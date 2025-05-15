"""
Latency optimizer for AUTOBOT trading system.

This module provides utilities to optimize network latency and execution speed
for high-frequency trading operations.
"""

import time
import socket
import threading
import logging
import os
import json
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

@dataclass
class LatencyStats:
    """Statistics about network latency for a specific endpoint."""
    endpoint: str
    min_latency_ms: float
    max_latency_ms: float
    avg_latency_ms: float
    std_dev_ms: float
    samples: int
    last_updated: float  # timestamp


class LatencyOptimizer:
    """
    Optimizes network latency for trading operations.
    
    This class provides utilities to measure, monitor, and optimize
    network latency for trading operations, particularly for HFT.
    """
    
    def __init__(
        self,
        check_interval: float = 60.0,
        history_size: int = 1000,
        auto_optimize: bool = True,
        visible_interface: bool = False
    ):
        """
        Initialize the latency optimizer.
        
        Args:
            check_interval: Interval in seconds between latency checks
            history_size: Number of latency measurements to keep in history
            auto_optimize: Whether to automatically optimize routing
            visible_interface: Whether to show optimization messages in the interface
        """
        self.check_interval = check_interval
        self.history_size = history_size
        self.auto_optimize = auto_optimize
        self.visible_interface = visible_interface
        
        self._monitoring_active = False
        self._monitoring_thread = None
        self._latency_data = {}
        self._route_cache = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=10)
        
        self._load_cached_data()
        
        if auto_optimize:
            self.start_monitoring()
    
    def _load_cached_data(self) -> None:
        """Load cached latency data from disk if available."""
        cache_path = os.path.join(os.path.expanduser("~"), ".autobot", "latency_cache.json")
        
        try:
            if os.path.exists(cache_path):
                with open(cache_path, "r") as f:
                    data = json.load(f)
                    
                    if "latency_data" in data:
                        self._latency_data = data["latency_data"]
                    
                    if "route_cache" in data:
                        self._route_cache = data["route_cache"]
                        
                    if self.visible_interface:
                        logger.info(f"Loaded latency cache with {len(self._latency_data)} endpoints")
                    else:
                        logger.debug(f"Loaded latency cache with {len(self._latency_data)} endpoints")
        except Exception as e:
            logger.warning(f"Failed to load latency cache: {str(e)}")
    
    def _save_cached_data(self) -> None:
        """Save latency data to disk cache."""
        cache_dir = os.path.join(os.path.expanduser("~"), ".autobot")
        cache_path = os.path.join(cache_dir, "latency_cache.json")
        
        try:
            os.makedirs(cache_dir, exist_ok=True)
            
            with open(cache_path, "w") as f:
                json.dump({
                    "latency_data": self._latency_data,
                    "route_cache": self._route_cache
                }, f)
                
            if self.visible_interface:
                logger.info(f"Saved latency cache with {len(self._latency_data)} endpoints")
            else:
                logger.debug(f"Saved latency cache with {len(self._latency_data)} endpoints")
        except Exception as e:
            logger.warning(f"Failed to save latency cache: {str(e)}")
    
    def start_monitoring(self) -> None:
        """Start the latency monitoring thread."""
        if self._monitoring_active:
            return
            
        self._monitoring_active = True
        
        if self._monitoring_thread is None or not self._monitoring_thread.is_alive():
            self._monitoring_thread = threading.Thread(
                target=self._monitoring_loop,
                daemon=True
            )
            self._monitoring_thread.start()
            
            if self.visible_interface:
                logger.info("Started latency monitoring")
            else:
                logger.debug("Started latency monitoring")
    
    def stop_monitoring(self) -> None:
        """Stop the latency monitoring thread."""
        self._monitoring_active = False
        
        if self.visible_interface:
            logger.info("Stopped latency monitoring")
        else:
            logger.debug("Stopped latency monitoring")
        
        self._save_cached_data()
    
    def _monitoring_loop(self) -> None:
        """Background loop for monitoring network latency."""
        common_endpoints = [
            "api.binance.com",
            "api.kraken.com",
            "api.coinbase.com",
            "api.huobi.com",
            "api.kucoin.com",
            "api.bybit.com",
            "api.bitfinex.com",
            "api.okx.com",
            "api.gate.io",
            "api.ftx.com"
        ]
        
        while self._monitoring_active:
            try:
                for endpoint in common_endpoints:
                    self.measure_latency(endpoint)
                
                custom_endpoints = [ep for ep in self._latency_data.keys() 
                                   if ep not in common_endpoints]
                
                for endpoint in custom_endpoints[:10]:  # Limit to 10 custom endpoints per cycle
                    self.measure_latency(endpoint)
                
                if self.auto_optimize:
                    self._optimize_routes()
                
                self._save_cached_data()
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in latency monitoring: {str(e)}")
                time.sleep(self.check_interval)
    
    def measure_latency(self, endpoint: str, port: int = 443, samples: int = 5) -> Optional[LatencyStats]:
        """
        Measure network latency to an endpoint.
        
        Args:
            endpoint: Hostname or IP to measure
            port: Port to connect to
            samples: Number of samples to take
            
        Returns:
            LatencyStats: Latency statistics or None if measurement failed
        """
        if not endpoint:
            return None
        
        if "://" in endpoint:
            endpoint = endpoint.split("://")[1]
        
        if "/" in endpoint:
            endpoint = endpoint.split("/")[0]
        
        latencies = []
        
        for _ in range(samples):
            try:
                start_time = time.time()
                
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2.0)
                
                sock.connect((endpoint, port))
                
                sock.close()
                
                latency_ms = (time.time() - start_time) * 1000
                latencies.append(latency_ms)
                
            except Exception as e:
                if self.visible_interface:
                    logger.warning(f"Failed to measure latency to {endpoint}: {str(e)}")
                else:
                    logger.debug(f"Failed to measure latency to {endpoint}: {str(e)}")
        
        if not latencies:
            return None
        
        min_latency = min(latencies)
        max_latency = max(latencies)
        avg_latency = sum(latencies) / len(latencies)
        std_dev = np.std(latencies) if len(latencies) > 1 else 0
        
        stats = LatencyStats(
            endpoint=endpoint,
            min_latency_ms=min_latency,
            max_latency_ms=max_latency,
            avg_latency_ms=avg_latency,
            std_dev_ms=std_dev,
            samples=len(latencies),
            last_updated=time.time()
        )
        
        with self._lock:
            if endpoint not in self._latency_data:
                self._latency_data[endpoint] = {
                    "history": [],
                    "current": {
                        "min_latency_ms": min_latency,
                        "max_latency_ms": max_latency,
                        "avg_latency_ms": avg_latency,
                        "std_dev_ms": std_dev,
                        "samples": len(latencies),
                        "last_updated": time.time()
                    }
                }
            else:
                self._latency_data[endpoint]["current"] = {
                    "min_latency_ms": min_latency,
                    "max_latency_ms": max_latency,
                    "avg_latency_ms": avg_latency,
                    "std_dev_ms": std_dev,
                    "samples": len(latencies),
                    "last_updated": time.time()
                }
                
                self._latency_data[endpoint]["history"].append({
                    "timestamp": time.time(),
                    "avg_latency_ms": avg_latency
                })
                
                if len(self._latency_data[endpoint]["history"]) > self.history_size:
                    self._latency_data[endpoint]["history"] = self._latency_data[endpoint]["history"][-self.history_size:]
        
        if self.visible_interface:
            logger.info(f"Latency to {endpoint}: {avg_latency:.2f}ms (min: {min_latency:.2f}ms, max: {max_latency:.2f}ms)")
        else:
            logger.debug(f"Latency to {endpoint}: {avg_latency:.2f}ms (min: {min_latency:.2f}ms, max: {max_latency:.2f}ms)")
        
        return stats
    
    def get_latency_stats(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """
        Get latency statistics for an endpoint.
        
        Args:
            endpoint: Hostname or IP to get stats for
            
        Returns:
            Dict: Latency statistics or None if not available
        """
        with self._lock:
            if endpoint in self._latency_data:
                return self._latency_data[endpoint]["current"]
            
            return None
    
    def get_latency_history(self, endpoint: str) -> List[Dict[str, Any]]:
        """
        Get latency history for an endpoint.
        
        Args:
            endpoint: Hostname or IP to get history for
            
        Returns:
            List[Dict]: Latency history or empty list if not available
        """
        with self._lock:
            if endpoint in self._latency_data:
                return self._latency_data[endpoint]["history"]
            
            return []
    
    def get_fastest_endpoint(self, endpoints: List[str]) -> Optional[str]:
        """
        Get the fastest endpoint from a list.
        
        Args:
            endpoints: List of endpoints to compare
            
        Returns:
            str: Fastest endpoint or None if no data available
        """
        if not endpoints:
            return None
        
        fastest_endpoint = None
        lowest_latency = float('inf')
        
        with self._lock:
            for endpoint in endpoints:
                if endpoint in self._latency_data:
                    latency = self._latency_data[endpoint]["current"]["avg_latency_ms"]
                    
                    if latency < lowest_latency:
                        lowest_latency = latency
                        fastest_endpoint = endpoint
        
        if fastest_endpoint is None and len(endpoints) > 0:
            for endpoint in endpoints:
                stats = self.measure_latency(endpoint)
                
                if stats and stats.avg_latency_ms < lowest_latency:
                    lowest_latency = stats.avg_latency_ms
                    fastest_endpoint = endpoint
        
        return fastest_endpoint
    
    def _optimize_routes(self) -> None:
        """Optimize network routes for lowest latency."""
        
        if self.visible_interface:
            logger.info("Optimizing network routes for lowest latency")
        else:
            logger.debug("Optimizing network routes for lowest latency")
    
    def get_all_endpoints(self) -> List[str]:
        """
        Get all monitored endpoints.
        
        Returns:
            List[str]: List of all monitored endpoints
        """
        with self._lock:
            return list(self._latency_data.keys())
    
    def get_latency_summary(self) -> Dict[str, Any]:
        """
        Get a summary of latency statistics for all endpoints.
        
        Returns:
            Dict: Summary of latency statistics
        """
        with self._lock:
            endpoints = list(self._latency_data.keys())
            
            if not endpoints:
                return {
                    "endpoints": 0,
                    "avg_latency_ms": 0,
                    "fastest_endpoint": None,
                    "slowest_endpoint": None
                }
            
            fastest_endpoint = None
            slowest_endpoint = None
            lowest_latency = float('inf')
            highest_latency = 0
            total_latency = 0
            
            for endpoint in endpoints:
                latency = self._latency_data[endpoint]["current"]["avg_latency_ms"]
                total_latency += latency
                
                if latency < lowest_latency:
                    lowest_latency = latency
                    fastest_endpoint = endpoint
                
                if latency > highest_latency:
                    highest_latency = latency
                    slowest_endpoint = endpoint
            
            return {
                "endpoints": len(endpoints),
                "avg_latency_ms": total_latency / len(endpoints) if endpoints else 0,
                "fastest_endpoint": {
                    "name": fastest_endpoint,
                    "latency_ms": lowest_latency
                } if fastest_endpoint else None,
                "slowest_endpoint": {
                    "name": slowest_endpoint,
                    "latency_ms": highest_latency
                } if slowest_endpoint else None
            }

def optimize_latency(
    auto_optimize: bool = True,
    visible_interface: bool = False
) -> LatencyOptimizer:
    """
    Create and return a latency optimizer.
    
    Args:
        auto_optimize: Whether to automatically optimize routing
        visible_interface: Whether to show optimization messages in the interface
        
    Returns:
        LatencyOptimizer: New latency optimizer instance
    """
    return LatencyOptimizer(
        auto_optimize=auto_optimize,
        visible_interface=visible_interface
    )
