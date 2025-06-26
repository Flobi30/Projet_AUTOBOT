"""
Network resilience module for AUTOBOT.

This module provides utilities to improve network resilience and reliability
for AUTOBOT's trading operations, especially in high-frequency trading scenarios.
"""

import time
import logging
import threading
import socket
import requests
import json
import os
import random
from typing import Dict, List, Any, Optional, Tuple, Callable
from datetime import datetime, timedelta
import numpy as np
from collections import deque

logger = logging.getLogger(__name__)

class NetworkResilience:
    """
    Network resilience manager for AUTOBOT.
    
    This class provides utilities to improve network resilience and reliability
    for AUTOBOT's trading operations, especially in high-frequency trading scenarios.
    """
    
    def __init__(
        self,
        check_interval: float = 5.0,
        connection_timeout: float = 3.0,
        retry_limit: int = 3,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_cooldown: float = 30.0,
        auto_optimize: bool = True,
        visible_interface: bool = True
    ):
        """
        Initialize the network resilience manager.
        
        Args:
            check_interval: Interval in seconds between network checks
            connection_timeout: Timeout in seconds for connection attempts
            retry_limit: Maximum number of retries for failed requests
            circuit_breaker_threshold: Number of failures before circuit breaker trips
            circuit_breaker_cooldown: Cooldown period in seconds for circuit breaker
            auto_optimize: Whether to automatically optimize network routes
            visible_interface: Whether to show network messages in the interface
        """
        self.check_interval = check_interval
        self.connection_timeout = connection_timeout
        self.retry_limit = retry_limit
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_cooldown = circuit_breaker_cooldown
        self.auto_optimize = auto_optimize
        self.visible_interface = visible_interface
        
        self._monitoring_active = False
        self._monitoring_thread = None
        self._endpoints = {}
        self._circuit_breakers = {}
        self._route_cache = {}
        self._latency_history = {}
        self._dns_cache = {}
        self._connection_pools = {}
        self._lock = threading.Lock()
        
        self._session = requests.Session()
        self._session.mount('https://', requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=100,
            max_retries=retry_limit,
            pool_block=False
        ))
        
        if auto_optimize:
            self.start_monitoring()
    
    def register_endpoint(
        self,
        name: str,
        url: str,
        priority: int = 1,
        health_check_path: str = "/health",
        alternatives: List[str] = None
    ) -> None:
        """
        Register a new endpoint for monitoring.
        
        Args:
            name: Name of the endpoint
            url: Base URL of the endpoint
            priority: Priority of the endpoint (1-10, higher is more important)
            health_check_path: Path to use for health checks
            alternatives: List of alternative URLs for the same service
        """
        with self._lock:
            self._endpoints[name] = {
                "url": url,
                "priority": priority,
                "health_check_path": health_check_path,
                "alternatives": alternatives or [],
                "status": "unknown",
                "last_check": 0,
                "latency": float('inf'),
                "success_count": 0,
                "failure_count": 0
            }
            
            self._circuit_breakers[name] = {
                "tripped": False,
                "failure_count": 0,
                "last_trip": 0,
                "cooldown_until": 0
            }
            
            self._latency_history[name] = deque(maxlen=100)
            
            self._resolve_dns(url)
            
            for alt_url in alternatives or []:
                self._resolve_dns(alt_url)
            
            if self.visible_interface:
                logger.info(f"Registered endpoint: {name} ({url})")
            else:
                logger.debug(f"Registered endpoint: {name} ({url})")
    
    def _resolve_dns(self, url: str) -> None:
        """
        Resolve DNS for a URL and cache the result.
        
        Args:
            url: URL to resolve
        """
        try:
            hostname = url.split("//")[-1].split("/")[0].split(":")[0]
            
            if hostname not in self._dns_cache or time.time() - self._dns_cache[hostname]["timestamp"] > 3600:
                ip_address = socket.gethostbyname(hostname)
                self._dns_cache[hostname] = {
                    "ip": ip_address,
                    "timestamp": time.time()
                }
                
                logger.debug(f"Resolved DNS for {hostname}: {ip_address}")
        except Exception as e:
            logger.error(f"Error resolving DNS for {url}: {str(e)}")
    
    def start_monitoring(self) -> None:
        """Start the network monitoring thread."""
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
                logger.info("Started network monitoring")
            else:
                logger.debug("Started network monitoring")
    
    def stop_monitoring(self) -> None:
        """Stop the network monitoring thread."""
        self._monitoring_active = False
        
        if self.visible_interface:
            logger.info("Stopped network monitoring")
        else:
            logger.debug("Stopped network monitoring")
    
    def _monitoring_loop(self) -> None:
        """Background loop for monitoring network endpoints."""
        while self._monitoring_active:
            try:
                for name, endpoint in self._endpoints.items():
                    if time.time() - endpoint["last_check"] < self.check_interval:
                        continue
                    
                    self._check_endpoint(name)
                
                if self.auto_optimize:
                    self._update_route_cache()
                
                time.sleep(1.0)  # Sleep briefly between iterations
                
            except Exception as e:
                logger.error(f"Error in network monitoring: {str(e)}")
                time.sleep(self.check_interval)
    
    def _check_endpoint(self, name: str) -> None:
        """
        Check the health of an endpoint.
        
        Args:
            name: Name of the endpoint to check
        """
        endpoint = self._endpoints[name]
        circuit_breaker = self._circuit_breakers[name]
        
        if circuit_breaker["tripped"]:
            if time.time() < circuit_breaker["cooldown_until"]:
                return
            else:
                circuit_breaker["tripped"] = False
                circuit_breaker["failure_count"] = 0
                
                if self.visible_interface:
                    logger.info(f"Circuit breaker reset for endpoint: {name}")
                else:
                    logger.debug(f"Circuit breaker reset for endpoint: {name}")
        
        primary_result = self._check_url(endpoint["url"] + endpoint["health_check_path"])
        
        if primary_result["success"]:
            endpoint["status"] = "healthy"
            endpoint["latency"] = primary_result["latency"]
            endpoint["last_check"] = time.time()
            endpoint["success_count"] += 1
            endpoint["failure_count"] = 0
            circuit_breaker["failure_count"] = 0
            
            self._latency_history[name].append(primary_result["latency"])
            
            return
        
        for alt_url in endpoint["alternatives"]:
            alt_result = self._check_url(alt_url + endpoint["health_check_path"])
            
            if alt_result["success"]:
                endpoint["status"] = "degraded"
                endpoint["latency"] = alt_result["latency"]
                endpoint["last_check"] = time.time()
                endpoint["success_count"] += 1
                
                self._latency_history[name].append(alt_result["latency"])
                
                endpoint["alternatives"].remove(alt_url)
                endpoint["alternatives"].append(endpoint["url"])
                endpoint["url"] = alt_url
                
                if self.visible_interface:
                    logger.warning(f"Switched to alternative URL for endpoint: {name} ({alt_url})")
                else:
                    logger.debug(f"Switched to alternative URL for endpoint: {name} ({alt_url})")
                
                return
        
        endpoint["status"] = "unhealthy"
        endpoint["latency"] = float('inf')
        endpoint["last_check"] = time.time()
        endpoint["failure_count"] += 1
        circuit_breaker["failure_count"] += 1
        
        if circuit_breaker["failure_count"] >= self.circuit_breaker_threshold:
            circuit_breaker["tripped"] = True
            circuit_breaker["last_trip"] = time.time()
            circuit_breaker["cooldown_until"] = time.time() + self.circuit_breaker_cooldown
            
            if self.visible_interface:
                logger.error(f"Circuit breaker tripped for endpoint: {name}")
            else:
                logger.debug(f"Circuit breaker tripped for endpoint: {name}")
    
    def _check_url(self, url: str) -> Dict[str, Any]:
        """
        Check the health of a URL.
        
        Args:
            url: URL to check
            
        Returns:
            Dict: Result of the health check
        """
        start_time = time.time()
        
        try:
            response = self._session.get(
                url,
                timeout=self.connection_timeout,
                headers={"User-Agent": "AUTOBOT-HealthCheck/1.0"}
            )
            
            latency = time.time() - start_time
            
            if response.status_code < 400:
                return {
                    "success": True,
                    "latency": latency,
                    "status_code": response.status_code
                }
            else:
                return {
                    "success": False,
                    "latency": latency,
                    "status_code": response.status_code,
                    "error": f"HTTP error: {response.status_code}"
                }
                
        except requests.exceptions.RequestException as e:
            latency = time.time() - start_time
            
            return {
                "success": False,
                "latency": latency,
                "error": str(e)
            }
    
    def _update_route_cache(self) -> None:
        """Update the route cache based on latest endpoint data."""
        with self._lock:
            for name, endpoint in self._endpoints.items():
                if endpoint["status"] != "unhealthy":
                    self._route_cache[name] = {
                        "url": endpoint["url"],
                        "latency": endpoint["latency"],
                        "timestamp": time.time()
                    }
    
    def get_endpoint(self, name: str) -> Optional[str]:
        """
        Get the best URL for an endpoint.
        
        Args:
            name: Name of the endpoint
            
        Returns:
            str: Best URL for the endpoint, or None if not available
        """
        with self._lock:
            if name not in self._endpoints:
                return None
            
            endpoint = self._endpoints[name]
            circuit_breaker = self._circuit_breakers[name]
            
            if circuit_breaker["tripped"] and time.time() < circuit_breaker["cooldown_until"]:
                return None
            
            if name in self._route_cache and time.time() - self._route_cache[name]["timestamp"] < 60:
                return self._route_cache[name]["url"]
            
            return endpoint["url"]
    
    def get_all_endpoints(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all endpoints.
        
        Returns:
            Dict: Status of all endpoints
        """
        with self._lock:
            result = {}
            
            for name, endpoint in self._endpoints.items():
                circuit_breaker = self._circuit_breakers[name]
                
                result[name] = {
                    "url": endpoint["url"],
                    "status": endpoint["status"],
                    "latency": endpoint["latency"],
                    "last_check": endpoint["last_check"],
                    "circuit_breaker": circuit_breaker["tripped"],
                    "alternatives": len(endpoint["alternatives"])
                }
            
            return result
    
    def get_latency_stats(self, name: str) -> Dict[str, Any]:
        """
        Get latency statistics for an endpoint.
        
        Args:
            name: Name of the endpoint
            
        Returns:
            Dict: Latency statistics
        """
        with self._lock:
            if name not in self._endpoints or not self._latency_history[name]:
                return {
                    "min": 0,
                    "max": 0,
                    "avg": 0,
                    "median": 0,
                    "p95": 0,
                    "p99": 0,
                    "samples": 0
                }
            
            latencies = list(self._latency_history[name])
            
            return {
                "min": min(latencies),
                "max": max(latencies),
                "avg": sum(latencies) / len(latencies),
                "median": np.median(latencies),
                "p95": np.percentile(latencies, 95),
                "p99": np.percentile(latencies, 99),
                "samples": len(latencies)
            }
    
    def execute_with_retry(
        self,
        func: Callable,
        *args,
        retry_limit: Optional[int] = None,
        retry_delay: float = 1.0,
        exponential_backoff: bool = True,
        **kwargs
    ) -> Any:
        """
        Execute a function with automatic retry on failure.
        
        Args:
            func: Function to execute
            *args: Arguments to pass to the function
            retry_limit: Maximum number of retries (defaults to instance retry_limit)
            retry_delay: Initial delay between retries in seconds
            exponential_backoff: Whether to use exponential backoff for retries
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            Any: Result of the function
            
        Raises:
            Exception: If all retries fail
        """
        if retry_limit is None:
            retry_limit = self.retry_limit
            
        last_exception = None
        
        for attempt in range(retry_limit + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt < retry_limit:
                    delay = retry_delay
                    
                    if exponential_backoff:
                        delay = retry_delay * (2 ** attempt)
                    
                    logger.debug(f"Retry attempt {attempt + 1}/{retry_limit} after {delay:.2f}s: {str(e)}")
                    time.sleep(delay)
        
        raise last_exception

def create_network_resilience(
    auto_optimize: bool = True,
    visible_interface: bool = True
) -> NetworkResilience:
    """
    Create and return a network resilience manager.
    
    Args:
        auto_optimize: Whether to automatically optimize network routes
        visible_interface: Whether to show network messages in the interface
        
    Returns:
        NetworkResilience: New network resilience manager instance
    """
    return NetworkResilience(
        auto_optimize=auto_optimize,
        visible_interface=visible_interface
    )
