"""
Data resilience module for AUTOBOT.

This module provides utilities to improve data resilience and reliability
for AUTOBOT's operations, ensuring data integrity and availability.
"""

import time
import logging
import threading
import json
import os
import hashlib
import random
import shutil
from typing import Dict, List, Any, Optional, Tuple, Callable, Union
from datetime import datetime, timedelta
import numpy as np
from collections import deque

logger = logging.getLogger(__name__)

class DataResilience:
    """
    Data resilience manager for AUTOBOT.
    
    This class provides utilities to improve data resilience and reliability
    for AUTOBOT's operations, ensuring data integrity and availability.
    """
    
    def __init__(
        self,
        data_dir: str = "data",
        backup_dir: str = "backups",
        check_interval: float = 60.0,
        backup_interval: float = 3600.0,
        integrity_check_interval: float = 300.0,
        auto_backup: bool = True,
        auto_recovery: bool = True,
        compression_level: int = 6,
        encryption_enabled: bool = False,
        visible_interface: bool = True
    ):
        """
        Initialize the data resilience manager.
        
        Args:
            data_dir: Directory for storing data
            backup_dir: Directory for storing backups
            check_interval: Interval in seconds between data checks
            backup_interval: Interval in seconds between backups
            integrity_check_interval: Interval in seconds between integrity checks
            auto_backup: Whether to automatically backup data
            auto_recovery: Whether to automatically recover corrupted data
            compression_level: Compression level for backups (0-9)
            encryption_enabled: Whether to encrypt backups
            visible_interface: Whether to show data messages in the interface
        """
        self.data_dir = os.path.abspath(data_dir)
        self.backup_dir = os.path.abspath(backup_dir)
        self.check_interval = check_interval
        self.backup_interval = backup_interval
        self.integrity_check_interval = integrity_check_interval
        self.auto_backup = auto_backup
        self.auto_recovery = auto_recovery
        self.compression_level = compression_level
        self.encryption_enabled = encryption_enabled
        self.visible_interface = visible_interface
        
        self._monitoring_active = False
        self._monitoring_thread = None
        self._data_registry = {}
        self._backup_registry = {}
        self._integrity_registry = {}
        self._lock = threading.Lock()
        
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        
        for subdir in ["models", "trading", "rl", "market", "user", "system"]:
            os.makedirs(os.path.join(self.data_dir, subdir), exist_ok=True)
            os.makedirs(os.path.join(self.backup_dir, subdir), exist_ok=True)
        
        if auto_backup:
            self.start_monitoring()
    
    def register_data(
        self,
        name: str,
        data_type: str,
        path: str,
        priority: int = 1,
        backup_frequency: float = None,
        integrity_check: bool = True,
        versioning: bool = True
    ) -> None:
        """
        Register data for monitoring and backup.
        
        Args:
            name: Name of the data
            data_type: Type of data (models, trading, rl, market, user, system)
            path: Path to the data file or directory
            priority: Priority of the data (1-10, higher is more important)
            backup_frequency: Custom backup frequency in seconds
            integrity_check: Whether to perform integrity checks
            versioning: Whether to keep multiple versions of backups
        """
        with self._lock:
            if data_type not in ["models", "trading", "rl", "market", "user", "system"]:
                data_type = "system"
            
            abs_path = os.path.abspath(path)
            
            self._data_registry[name] = {
                "type": data_type,
                "path": abs_path,
                "priority": priority,
                "backup_frequency": backup_frequency or self.backup_interval,
                "integrity_check": integrity_check,
                "versioning": versioning,
                "last_backup": 0,
                "last_check": 0,
                "checksum": self._calculate_checksum(abs_path) if os.path.exists(abs_path) else None,
                "size": self._get_size(abs_path) if os.path.exists(abs_path) else 0,
                "status": "registered"
            }
            
            if self.visible_interface:
                logger.info(f"Registered data: {name} ({data_type})")
            else:
                logger.debug(f"Registered data: {name} ({data_type})")
    
    def _calculate_checksum(self, path: str) -> Optional[str]:
        """
        Calculate checksum for a file or directory.
        
        Args:
            path: Path to file or directory
            
        Returns:
            str: Checksum of the file or directory
        """
        if not os.path.exists(path):
            return None
        
        if os.path.isfile(path):
            try:
                hasher = hashlib.sha256()
                with open(path, 'rb') as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hasher.update(chunk)
                return hasher.hexdigest()
            except Exception as e:
                logger.error(f"Error calculating checksum for {path}: {str(e)}")
                return None
        
        elif os.path.isdir(path):
            try:
                hasher = hashlib.sha256()
                for root, dirs, files in os.walk(path):
                    for file in sorted(files):
                        file_path = os.path.join(root, file)
                        if os.path.isfile(file_path):
                            hasher.update(file_path.encode())
                            with open(file_path, 'rb') as f:
                                for chunk in iter(lambda: f.read(4096), b""):
                                    hasher.update(chunk)
                return hasher.hexdigest()
            except Exception as e:
                logger.error(f"Error calculating checksum for directory {path}: {str(e)}")
                return None
        
        return None
    
    def _get_size(self, path: str) -> int:
        """
        Get size of a file or directory in bytes.
        
        Args:
            path: Path to file or directory
            
        Returns:
            int: Size in bytes
        """
        if not os.path.exists(path):
            return 0
        
        if os.path.isfile(path):
            return os.path.getsize(path)
        
        elif os.path.isdir(path):
            total_size = 0
            for root, dirs, files in os.walk(path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.isfile(file_path):
                        total_size += os.path.getsize(file_path)
            return total_size
        
        return 0
    
    def start_monitoring(self) -> None:
        """Start the data monitoring thread."""
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
                logger.info("Started data monitoring")
            else:
                logger.debug("Started data monitoring")
    
    def stop_monitoring(self) -> None:
        """Stop the data monitoring thread."""
        self._monitoring_active = False
        
        if self.visible_interface:
            logger.info("Stopped data monitoring")
        else:
            logger.debug("Stopped data monitoring")
    
    def _monitoring_loop(self) -> None:
        """Background loop for monitoring data."""
        while self._monitoring_active:
            try:
                current_time = time.time()
                
                for name, data in self._data_registry.items():
                    if not os.path.exists(data["path"]):
                        continue
                    
                    if current_time - data["last_backup"] >= data["backup_frequency"]:
                        self._backup_data(name)
                    
                    if data["integrity_check"] and current_time - data["last_check"] >= self.integrity_check_interval:
                        self._check_integrity(name)
                
                time.sleep(1.0)
                
            except Exception as e:
                logger.error(f"Error in data monitoring: {str(e)}")
                time.sleep(self.check_interval)
    
    def _backup_data(self, name: str) -> bool:
        """
        Backup data.
        
        Args:
            name: Name of the data to backup
            
        Returns:
            bool: Whether backup was successful
        """
        with self._lock:
            if name not in self._data_registry:
                return False
            
            data = self._data_registry[name]
            
            if not os.path.exists(data["path"]):
                return False
            
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_filename = f"{name}_{timestamp}"
                
                backup_path = os.path.join(self.backup_dir, data["type"], backup_filename)
                
                if os.path.isfile(data["path"]):
                    shutil.copy2(data["path"], backup_path)
                elif os.path.isdir(data["path"]):
                    shutil.copytree(data["path"], backup_path)
                
                self._backup_registry[backup_filename] = {
                    "name": name,
                    "type": data["type"],
                    "path": backup_path,
                    "original_path": data["path"],
                    "timestamp": time.time(),
                    "checksum": self._calculate_checksum(backup_path),
                    "size": self._get_size(backup_path)
                }
                
                data["last_backup"] = time.time()
                data["status"] = "backed_up"
                
                if not data["versioning"]:
                    self._cleanup_old_backups(name)
                
                if self.visible_interface:
                    logger.info(f"Backed up data: {name}")
                else:
                    logger.debug(f"Backed up data: {name}")
                
                return True
                
            except Exception as e:
                logger.error(f"Error backing up data {name}: {str(e)}")
                return False
    
    def _cleanup_old_backups(self, name: str) -> None:
        """
        Clean up old backups for a data item.
        
        Args:
            name: Name of the data
        """
        backups = []
        
        for backup_name, backup in self._backup_registry.items():
            if backup["name"] == name:
                backups.append((backup_name, backup["timestamp"]))
        
        backups.sort(key=lambda x: x[1], reverse=True)
        
        for backup_name, _ in backups[1:]:
            backup = self._backup_registry[backup_name]
            
            try:
                if os.path.isfile(backup["path"]):
                    os.remove(backup["path"])
                elif os.path.isdir(backup["path"]):
                    shutil.rmtree(backup["path"])
                
                del self._backup_registry[backup_name]
                
                logger.debug(f"Removed old backup: {backup_name}")
                
            except Exception as e:
                logger.error(f"Error removing old backup {backup_name}: {str(e)}")
    
    def _check_integrity(self, name: str) -> bool:
        """
        Check integrity of data.
        
        Args:
            name: Name of the data to check
            
        Returns:
            bool: Whether data is intact
        """
        with self._lock:
            if name not in self._data_registry:
                return False
            
            data = self._data_registry[name]
            
            if not os.path.exists(data["path"]):
                return False
            
            try:
                current_checksum = self._calculate_checksum(data["path"])
                
                data["last_check"] = time.time()
                
                if data["checksum"] is None:
                    data["checksum"] = current_checksum
                    data["status"] = "checked"
                    return True
                
                if current_checksum == data["checksum"]:
                    data["status"] = "intact"
                    
                    if self.visible_interface:
                        logger.info(f"Data integrity verified: {name}")
                    else:
                        logger.debug(f"Data integrity verified: {name}")
                    
                    return True
                else:
                    data["status"] = "corrupted"
                    
                    logger.warning(f"Data integrity check failed for {name}")
                    
                    if self.auto_recovery:
                        self._recover_data(name)
                    
                    return False
                
            except Exception as e:
                logger.error(f"Error checking integrity for {name}: {str(e)}")
                return False
    
    def _recover_data(self, name: str) -> bool:
        """
        Recover corrupted data from backup.
        
        Args:
            name: Name of the data to recover
            
        Returns:
            bool: Whether recovery was successful
        """
        with self._lock:
            if name not in self._data_registry:
                return False
            
            backups = []
            
            for backup_name, backup in self._backup_registry.items():
                if backup["name"] == name:
                    backups.append((backup_name, backup["timestamp"]))
            
            if not backups:
                logger.error(f"No backups found for {name}, cannot recover")
                return False
            
            backups.sort(key=lambda x: x[1], reverse=True)
            
            for backup_name, _ in backups:
                backup = self._backup_registry[backup_name]
                
                try:
                    data = self._data_registry[name]
                    
                    recovery_path = data["path"] + ".recovered"
                    
                    if os.path.isfile(backup["path"]):
                        shutil.copy2(backup["path"], recovery_path)
                    elif os.path.isdir(backup["path"]):
                        if os.path.exists(recovery_path):
                            shutil.rmtree(recovery_path)
                        shutil.copytree(backup["path"], recovery_path)
                    
                    recovery_checksum = self._calculate_checksum(recovery_path)
                    
                    if recovery_checksum == backup["checksum"]:
                        corrupted_path = data["path"] + ".corrupted"
                        
                        if os.path.exists(corrupted_path):
                            if os.path.isfile(corrupted_path):
                                os.remove(corrupted_path)
                            elif os.path.isdir(corrupted_path):
                                shutil.rmtree(corrupted_path)
                        
                        if os.path.isfile(data["path"]):
                            shutil.move(data["path"], corrupted_path)
                        elif os.path.isdir(data["path"]):
                            shutil.move(data["path"], corrupted_path)
                        
                        if os.path.isfile(recovery_path):
                            shutil.move(recovery_path, data["path"])
                        elif os.path.isdir(recovery_path):
                            shutil.move(recovery_path, data["path"])
                        
                        data["checksum"] = recovery_checksum
                        data["status"] = "recovered"
                        
                        if self.visible_interface:
                            logger.info(f"Recovered data: {name} from backup {backup_name}")
                        else:
                            logger.debug(f"Recovered data: {name} from backup {backup_name}")
                        
                        return True
                    else:
                        if os.path.isfile(recovery_path):
                            os.remove(recovery_path)
                        elif os.path.isdir(recovery_path):
                            shutil.rmtree(recovery_path)
                        
                        logger.warning(f"Recovery verification failed for {name} using backup {backup_name}")
                    
                except Exception as e:
                    logger.error(f"Error recovering {name} from backup {backup_name}: {str(e)}")
            
            logger.error(f"All recovery attempts failed for {name}")
            return False
    
    def backup_all(self) -> Dict[str, bool]:
        """
        Backup all registered data.
        
        Returns:
            Dict: Results of backup operations
        """
        results = {}
        
        for name in self._data_registry.keys():
            results[name] = self._backup_data(name)
        
        return results
    
    def check_all(self) -> Dict[str, bool]:
        """
        Check integrity of all registered data.
        
        Returns:
            Dict: Results of integrity checks
        """
        results = {}
        
        for name in self._data_registry.keys():
            results[name] = self._check_integrity(name)
        
        return results
    
    def get_data_status(self, name: str = None) -> Union[Dict[str, Any], Dict[str, Dict[str, Any]]]:
        """
        Get status of data.
        
        Args:
            name: Name of the data, or None for all data
            
        Returns:
            Dict: Status of data
        """
        with self._lock:
            if name is not None:
                if name not in self._data_registry:
                    return {}
                
                data = self._data_registry[name]
                
                return {
                    "name": name,
                    "type": data["type"],
                    "path": data["path"],
                    "status": data["status"],
                    "size": data["size"],
                    "last_backup": data["last_backup"],
                    "last_check": data["last_check"]
                }
            else:
                result = {}
                
                for name, data in self._data_registry.items():
                    result[name] = {
                        "type": data["type"],
                        "path": data["path"],
                        "status": data["status"],
                        "size": data["size"],
                        "last_backup": data["last_backup"],
                        "last_check": data["last_check"]
                    }
                
                return result
    
    def get_backup_status(self, name: str = None) -> Union[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
        """
        Get status of backups.
        
        Args:
            name: Name of the data, or None for all backups
            
        Returns:
            Union[List, Dict]: Status of backups
        """
        with self._lock:
            if name is not None:
                result = []
                
                for backup_name, backup in self._backup_registry.items():
                    if backup["name"] == name:
                        result.append({
                            "backup_name": backup_name,
                            "timestamp": backup["timestamp"],
                            "path": backup["path"],
                            "size": backup["size"]
                        })
                
                result.sort(key=lambda x: x["timestamp"], reverse=True)
                
                return result
            else:
                result = {}
                
                for backup_name, backup in self._backup_registry.items():
                    if backup["name"] not in result:
                        result[backup["name"]] = []
                    
                    result[backup["name"]].append({
                        "backup_name": backup_name,
                        "timestamp": backup["timestamp"],
                        "path": backup["path"],
                        "size": backup["size"]
                    })
                
                for name in result:
                    result[name].sort(key=lambda x: x["timestamp"], reverse=True)
                
                return result

def create_data_resilience(
    data_dir: str = "data",
    backup_dir: str = "backups",
    auto_backup: bool = True,
    auto_recovery: bool = True,
    visible_interface: bool = True
) -> DataResilience:
    """
    Create and return a data resilience manager.
    
    Args:
        data_dir: Directory for storing data
        backup_dir: Directory for storing backups
        auto_backup: Whether to automatically backup data
        auto_recovery: Whether to automatically recover corrupted data
        visible_interface: Whether to show data messages in the interface
        
    Returns:
        DataResilience: New data resilience manager instance
    """
    return DataResilience(
        data_dir=data_dir,
        backup_dir=backup_dir,
        auto_backup=auto_backup,
        auto_recovery=auto_recovery,
        visible_interface=visible_interface
    )
