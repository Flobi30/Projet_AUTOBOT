"""
Ghosting Manager for AUTOBOT HFT Module

This module provides advanced instance duplication (ghosting) capabilities for
high-frequency trading operations, with license-based control and management.
"""

import os
import uuid
import json
import time
import logging
import threading
import multiprocessing
import socket
import hashlib
from typing import Dict, List, Any, Optional, Tuple, Union, Callable
from dataclasses import dataclass
from enum import Enum
import numpy as np

from ..autobot_security.license_manager import LicenseManager

logger = logging.getLogger(__name__)

class GhostingMode(Enum):
    """Ghosting operation modes"""
    DISABLED = 0
    PASSIVE = 1  # Read-only, no order execution
    ACTIVE = 2   # Full trading capabilities
    HYBRID = 3   # Mixed mode with selective execution


@dataclass
class GhostInstance:
    """Represents a ghost instance"""
    instance_id: str
    parent_id: str
    mode: GhostingMode
    created_at: int
    last_heartbeat: int
    status: str
    ip_address: str
    port: int
    cpu_usage: float
    memory_usage: float
    order_count: int
    trade_count: int
    profit_loss: float
    markets: List[str]
    strategies: List[str]
    config: Dict[str, Any]


class GhostingManager:
    """
    Advanced ghosting manager for AUTOBOT HFT operations.
    
    Provides capabilities for controlled instance duplication with
    license-based limits and remote management.
    """
    
    def __init__(
        self,
        license_manager: LicenseManager,
        data_dir: str = "data/ghosting",
        heartbeat_interval: int = 5,
        cleanup_interval: int = 60,
        max_instances: Optional[int] = None,
        default_mode: GhostingMode = GhostingMode.PASSIVE
    ):
        """
        Initialize the ghosting manager.
        
        Args:
            license_manager: License manager instance
            data_dir: Directory for storing ghosting data
            heartbeat_interval: Interval in seconds for heartbeat checks
            cleanup_interval: Interval in seconds for cleanup operations
            max_instances: Maximum number of instances, or None to use license limit
            default_mode: Default ghosting mode for new instances
        """
        self.license_manager = license_manager
        self.data_dir = data_dir
        self.heartbeat_interval = heartbeat_interval
        self.cleanup_interval = cleanup_interval
        self.max_instances = max_instances
        self.default_mode = default_mode
        
        self.instance_id = self._generate_instance_id()
        self.is_parent = True
        self.parent_id = None
        
        self.instances: Dict[str, GhostInstance] = {}
        self.workers: Dict[str, multiprocessing.Process] = {}
        self.instance_locks: Dict[str, threading.Lock] = {}
        
        self.running = True
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop)
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop)
        
        os.makedirs(data_dir, exist_ok=True)
        
        self._load_instances()
        
        self.heartbeat_thread.daemon = True
        self.cleanup_thread.daemon = True
        self.heartbeat_thread.start()
        self.cleanup_thread.start()
        
        logger.info(f"Ghosting Manager initialized with instance ID: {self.instance_id}")
    
    def _generate_instance_id(self) -> str:
        """
        Generate a unique instance ID.
        
        Returns:
            str: Unique instance ID
        """
        try:
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)
            
            unique_id = f"{hostname}-{ip_address}-{uuid.uuid4()}"
            return hashlib.sha256(unique_id.encode()).hexdigest()[:16]
            
        except Exception as e:
            logger.warning(f"Error generating hardware-based instance ID: {str(e)}")
            
            return str(uuid.uuid4())[:16]
    
    def _load_instances(self) -> None:
        """Load instances from file"""
        instances_file = os.path.join(self.data_dir, "instances.json")
        if os.path.exists(instances_file):
            try:
                with open(instances_file, 'r') as f:
                    instances_data = json.load(f)
                
                for instance_id, instance_data in instances_data.items():
                    self.instances[instance_id] = GhostInstance(
                        instance_id=instance_id,
                        parent_id=instance_data["parent_id"],
                        mode=GhostingMode(instance_data["mode"]),
                        created_at=instance_data["created_at"],
                        last_heartbeat=instance_data["last_heartbeat"],
                        status=instance_data["status"],
                        ip_address=instance_data["ip_address"],
                        port=instance_data["port"],
                        cpu_usage=instance_data["cpu_usage"],
                        memory_usage=instance_data["memory_usage"],
                        order_count=instance_data["order_count"],
                        trade_count=instance_data["trade_count"],
                        profit_loss=instance_data["profit_loss"],
                        markets=instance_data["markets"],
                        strategies=instance_data["strategies"],
                        config=instance_data["config"]
                    )
                    self.instance_locks[instance_id] = threading.Lock()
                
                logger.info(f"Loaded {len(self.instances)} instances from {instances_file}")
            except Exception as e:
                logger.error(f"Error loading instances from {instances_file}: {str(e)}")
    
    def _save_instances(self) -> None:
        """Save instances to file"""
        instances_file = os.path.join(self.data_dir, "instances.json")
        try:
            instances_data = {}
            for instance_id, instance in self.instances.items():
                instances_data[instance_id] = {
                    "parent_id": instance.parent_id,
                    "mode": instance.mode.value,
                    "created_at": instance.created_at,
                    "last_heartbeat": instance.last_heartbeat,
                    "status": instance.status,
                    "ip_address": instance.ip_address,
                    "port": instance.port,
                    "cpu_usage": instance.cpu_usage,
                    "memory_usage": instance.memory_usage,
                    "order_count": instance.order_count,
                    "trade_count": instance.trade_count,
                    "profit_loss": instance.profit_loss,
                    "markets": instance.markets,
                    "strategies": instance.strategies,
                    "config": instance.config
                }
            
            with open(instances_file, 'w') as f:
                json.dump(instances_data, f, indent=2)
            
            logger.debug(f"Saved {len(self.instances)} instances to {instances_file}")
        except Exception as e:
            logger.error(f"Error saving instances to {instances_file}: {str(e)}")
    
    def _heartbeat_loop(self) -> None:
        """Background thread for sending heartbeats"""
        while self.running:
            try:
                self._send_heartbeat()
                time.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {str(e)}")
                time.sleep(1)
    
    def _cleanup_loop(self) -> None:
        """Background thread for cleaning up dead instances"""
        while self.running:
            try:
                self._cleanup_instances()
                time.sleep(self.cleanup_interval)
            except Exception as e:
                logger.error(f"Error in cleanup loop: {str(e)}")
                time.sleep(1)
    
    def _send_heartbeat(self) -> None:
        """Send heartbeat for this instance"""
        if not self.is_parent:
            current_time = int(time.time())
            
            try:
                if self.instance_id in self.instances:
                    with self.instance_locks[self.instance_id]:
                        self.instances[self.instance_id].last_heartbeat = current_time
                        self.instances[self.instance_id].status = "active"
                
                logger.debug(f"Sent heartbeat at {current_time}")
            except Exception as e:
                logger.error(f"Error sending heartbeat: {str(e)}")
    
    def _cleanup_instances(self) -> None:
        """Clean up dead instances"""
        if not self.is_parent:
            return
        
        current_time = int(time.time())
        dead_instances = []
        
        for instance_id, instance in self.instances.items():
            if instance.status == "active" and current_time - instance.last_heartbeat > self.heartbeat_interval * 3:
                with self.instance_locks[instance_id]:
                    instance.status = "inactive"
                    logger.warning(f"Instance {instance_id} marked as inactive due to missed heartbeats")
            
            if instance.status == "inactive" and current_time - instance.last_heartbeat > self.cleanup_interval * 2:
                dead_instances.append(instance_id)
        
        for instance_id in dead_instances:
            self.terminate_instance(instance_id)
        
        if dead_instances:
            logger.info(f"Cleaned up {len(dead_instances)} dead instances")
    
    def create_instance(
        self,
        markets: List[str],
        strategies: List[str],
        config: Dict[str, Any],
        mode: Optional[GhostingMode] = None
    ) -> Optional[str]:
        """
        Create a new ghost instance.
        
        Args:
            markets: List of markets to trade on
            strategies: List of strategies to use
            config: Configuration for the instance
            mode: Ghosting mode, or None to use default
            
        Returns:
            str: Instance ID if creation was successful, None otherwise
        """
        if not self.is_parent:
            logger.error("Only parent instances can create new instances")
            return None
        
        if not self.license_manager.is_feature_enabled("ghosting"):
            logger.error("Ghosting feature is not enabled in the license")
            return None
        
        max_instances = self.max_instances
        if max_instances is None:
            license_info = self.license_manager.get_license_info()
            if "features" in license_info and "ghosting" in license_info["features"]:
                max_instances = license_info["features"]["ghosting"].get("max_usage", 1)
            else:
                max_instances = 1
        
        active_instances = len([i for i in self.instances.values() if i.status == "active"])
        if active_instances >= max_instances:
            logger.error(f"Cannot create new instance: reached limit of {max_instances} instances")
            return None
        
        if not self.license_manager.use_feature("ghosting"):
            logger.error("Failed to record ghosting feature usage")
            return None
        
        instance_id = self._generate_instance_id()
        current_time = int(time.time())
        
        instance = GhostInstance(
            instance_id=instance_id,
            parent_id=self.instance_id,
            mode=mode or self.default_mode,
            created_at=current_time,
            last_heartbeat=current_time,
            status="initializing",
            ip_address="127.0.0.1",  # This would be set properly in a real implementation
            port=8000 + len(self.instances),  # This would be set properly in a real implementation
            cpu_usage=0.0,
            memory_usage=0.0,
            order_count=0,
            trade_count=0,
            profit_loss=0.0,
            markets=markets,
            strategies=strategies,
            config=config
        )
        
        self.instances[instance_id] = instance
        self.instance_locks[instance_id] = threading.Lock()
        
        try:
            worker = multiprocessing.Process(
                target=self._instance_worker,
                args=(instance_id, markets, strategies, config, mode or self.default_mode)
            )
            worker.daemon = True
            worker.start()
            
            self.workers[instance_id] = worker
            
            logger.info(f"Created new instance {instance_id} with mode {instance.mode.name}")
            
            with self.instance_locks[instance_id]:
                instance.status = "active"
            
            self._save_instances()
            
            return instance_id
        except Exception as e:
            logger.error(f"Error starting worker process for instance {instance_id}: {str(e)}")
            self.instances.pop(instance_id, None)
            self.instance_locks.pop(instance_id, None)
            return None
    
    def _instance_worker(
        self,
        instance_id: str,
        markets: List[str],
        strategies: List[str],
        config: Dict[str, Any],
        mode: GhostingMode
    ) -> None:
        """
        Worker process for a ghost instance.
        
        Args:
            instance_id: Instance ID
            markets: List of markets to trade on
            strategies: List of strategies to use
            config: Configuration for the instance
            mode: Ghosting mode
        """
        try:
            self.instance_id = instance_id
            self.is_parent = False
            self.parent_id = self.instances[instance_id].parent_id
            
            logger.info(f"Ghost instance {instance_id} started with mode {mode.name}")
            
            while True:
                for market in markets:
                    for strategy in strategies:
                        self._execute_strategy(market, strategy, config, mode)
                
                self._update_metrics(instance_id)
                
                time.sleep(config.get("interval", 1))
        except Exception as e:
            logger.error(f"Error in ghost instance {instance_id}: {str(e)}")
    
    def _execute_strategy(
        self,
        market: str,
        strategy: str,
        config: Dict[str, Any],
        mode: GhostingMode
    ) -> None:
        """
        Execute a trading strategy.
        
        Args:
            market: Market to trade on
            strategy: Strategy to use
            config: Configuration for the instance
            mode: Ghosting mode
        """
        
        if mode == GhostingMode.DISABLED:
            return
        
        if mode == GhostingMode.ACTIVE or mode == GhostingMode.HYBRID:
            if np.random.random() < 0.1:  # 10% chance of placing an order
                logger.debug(f"Placed order for {market} using {strategy}")
                
                with self.instance_locks[self.instance_id]:
                    instance = self.instances[self.instance_id]
                    instance.order_count += 1
                    
                    if np.random.random() < 0.8:  # 80% chance of order being filled
                        instance.trade_count += 1
                        
                        pnl = np.random.normal(0.01, 0.05)  # Mean 1% profit, std dev 5%
                        instance.profit_loss += pnl
    
    def _update_metrics(self, instance_id: str) -> None:
        """
        Update metrics for an instance.
        
        Args:
            instance_id: Instance ID
        """
        try:
            cpu_usage = np.random.uniform(5, 30)  # Simulated CPU usage between 5% and 30%
            memory_usage = np.random.uniform(100, 500)  # Simulated memory usage between 100MB and 500MB
            
            with self.instance_locks[instance_id]:
                instance = self.instances[instance_id]
                instance.cpu_usage = cpu_usage
                instance.memory_usage = memory_usage
                instance.last_heartbeat = int(time.time())
        except Exception as e:
            logger.error(f"Error updating metrics for instance {instance_id}: {str(e)}")
    
    def terminate_instance(self, instance_id: str) -> bool:
        """
        Terminate a ghost instance.
        
        Args:
            instance_id: Instance ID
            
        Returns:
            bool: True if termination was successful
        """
        if instance_id not in self.instances:
            logger.error(f"Instance {instance_id} not found")
            return False
        
        try:
            if instance_id in self.workers:
                worker = self.workers[instance_id]
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=5)
                
                self.workers.pop(instance_id)
            
            self.instances.pop(instance_id)
            self.instance_locks.pop(instance_id, None)
            
            self._save_instances()
            
            logger.info(f"Terminated instance {instance_id}")
            return True
        except Exception as e:
            logger.error(f"Error terminating instance {instance_id}: {str(e)}")
            return False
    
    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about an instance.
        
        Args:
            instance_id: Instance ID
            
        Returns:
            Dict: Instance information
        """
        if instance_id not in self.instances:
            return None
        
        with self.instance_locks[instance_id]:
            instance = self.instances[instance_id]
            
            return {
                "instance_id": instance.instance_id,
                "parent_id": instance.parent_id,
                "mode": instance.mode.name,
                "created_at": instance.created_at,
                "last_heartbeat": instance.last_heartbeat,
                "status": instance.status,
                "ip_address": instance.ip_address,
                "port": instance.port,
                "cpu_usage": instance.cpu_usage,
                "memory_usage": instance.memory_usage,
                "order_count": instance.order_count,
                "trade_count": instance.trade_count,
                "profit_loss": instance.profit_loss,
                "markets": instance.markets,
                "strategies": instance.strategies
            }
    
    def get_instances(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get information about all instances.
        
        Args:
            status: Filter by status, or None for all instances
            
        Returns:
            List: List of instance information
        """
        instances_info = []
        
        for instance_id, instance in self.instances.items():
            if status is None or instance.status == status:
                with self.instance_locks[instance_id]:
                    instances_info.append({
                        "instance_id": instance.instance_id,
                        "parent_id": instance.parent_id,
                        "mode": instance.mode.name,
                        "created_at": instance.created_at,
                        "last_heartbeat": instance.last_heartbeat,
                        "status": instance.status,
                        "ip_address": instance.ip_address,
                        "port": instance.port,
                        "cpu_usage": instance.cpu_usage,
                        "memory_usage": instance.memory_usage,
                        "order_count": instance.order_count,
                        "trade_count": instance.trade_count,
                        "profit_loss": instance.profit_loss,
                        "markets": instance.markets,
                        "strategies": instance.strategies
                    })
        
        return instances_info
    
    def update_instance_config(self, instance_id: str, config: Dict[str, Any]) -> bool:
        """
        Update configuration for an instance.
        
        Args:
            instance_id: Instance ID
            config: New configuration
            
        Returns:
            bool: True if update was successful
        """
        if instance_id not in self.instances:
            logger.error(f"Instance {instance_id} not found")
            return False
        
        try:
            with self.instance_locks[instance_id]:
                self.instances[instance_id].config.update(config)
            
            self._save_instances()
            
            logger.info(f"Updated configuration for instance {instance_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating configuration for instance {instance_id}: {str(e)}")
            return False
    
    def update_instance_mode(self, instance_id: str, mode: GhostingMode) -> bool:
        """
        Update mode for an instance.
        
        Args:
            instance_id: Instance ID
            mode: New mode
            
        Returns:
            bool: True if update was successful
        """
        if instance_id not in self.instances:
            logger.error(f"Instance {instance_id} not found")
            return False
        
        try:
            with self.instance_locks[instance_id]:
                self.instances[instance_id].mode = mode
            
            self._save_instances()
            
            logger.info(f"Updated mode for instance {instance_id} to {mode.name}")
            return True
        except Exception as e:
            logger.error(f"Error updating mode for instance {instance_id}: {str(e)}")
            return False
    
    def get_total_metrics(self) -> Dict[str, Any]:
        """
        Get total metrics across all active instances.
        
        Returns:
            Dict: Total metrics
        """
        total_order_count = 0
        total_trade_count = 0
        total_profit_loss = 0.0
        total_cpu_usage = 0.0
        total_memory_usage = 0.0
        active_count = 0
        
        for instance in self.instances.values():
            if instance.status == "active":
                total_order_count += instance.order_count
                total_trade_count += instance.trade_count
                total_profit_loss += instance.profit_loss
                total_cpu_usage += instance.cpu_usage
                total_memory_usage += instance.memory_usage
                active_count += 1
        
        return {
            "active_instances": active_count,
            "total_instances": len(self.instances),
            "total_order_count": total_order_count,
            "total_trade_count": total_trade_count,
            "total_profit_loss": total_profit_loss,
            "avg_cpu_usage": total_cpu_usage / active_count if active_count > 0 else 0,
            "avg_memory_usage": total_memory_usage / active_count if active_count > 0 else 0,
            "fill_rate": total_trade_count / total_order_count if total_order_count > 0 else 0
        }
    
    def shutdown(self) -> None:
        """Shutdown the ghosting manager"""
        self.running = False
        
        for instance_id in list(self.instances.keys()):
            self.terminate_instance(instance_id)
        
        if self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=1)
        
        if self.cleanup_thread.is_alive():
            self.cleanup_thread.join(timeout=1)
        
        logger.info("Ghosting Manager shut down")


def create_ghosting_manager(
    license_manager: LicenseManager,
    max_instances: Optional[int] = None
) -> GhostingManager:
    """
    Create a new ghosting manager.
    
    Args:
        license_manager: License manager instance
        max_instances: Maximum number of instances, or None to use license limit
        
    Returns:
        GhostingManager: New ghosting manager instance
    """
    return GhostingManager(
        license_manager=license_manager,
        max_instances=max_instances
    )
