"""
Thread Management Integration for Ghosting Manager

This module integrates the thread management system with the ghosting manager
to ensure proper thread cleanup during CI and prevent segmentation faults.
"""

import os
import logging
import threading
import time
from typing import Dict, Any, Optional, List

from ..thread_management import (
    create_managed_thread,
    is_shutdown_requested,
    register_thread,
    unregister_thread,
    ManagedThread
)

logger = logging.getLogger(__name__)

class GhostingThreadManager:
    """
    Thread management integration for ghosting manager.
    
    This class provides methods to integrate the thread management system
    with the ghosting manager, ensuring proper thread cleanup during CI
    and preventing segmentation faults.
    """
    
    def __init__(self):
        """
        Initialize the ghosting thread manager.
        """
        self.threads: Dict[str, ManagedThread] = {}
        self.thread_locks: Dict[str, threading.Lock] = {}
        logger.info("Ghosting thread manager initialized")
    
    def create_heartbeat_thread(self, target, name="ghosting_heartbeat") -> ManagedThread:
        """
        Create a managed heartbeat thread.
        
        Args:
            target: Thread target function
            name: Thread name
            
        Returns:
            ManagedThread: Managed thread instance
        """
        thread = create_managed_thread(
            name=name,
            target=target,
            daemon=True,
            auto_start=True,
            cleanup_callback=lambda: logger.debug(f"Cleaned up {name} thread")
        )
        
        self.threads[name] = thread
        return thread
    
    def create_cleanup_thread(self, target, name="ghosting_cleanup") -> ManagedThread:
        """
        Create a managed cleanup thread.
        
        Args:
            target: Thread target function
            name: Thread name
            
        Returns:
            ManagedThread: Managed thread instance
        """
        thread = create_managed_thread(
            name=name,
            target=target,
            daemon=True,
            auto_start=True,
            cleanup_callback=lambda: logger.debug(f"Cleaned up {name} thread")
        )
        
        self.threads[name] = thread
        return thread
    
    def create_worker_thread(self, target, name, args=None) -> ManagedThread:
        """
        Create a managed worker thread.
        
        Args:
            target: Thread target function
            name: Thread name
            args: Thread arguments
            
        Returns:
            ManagedThread: Managed thread instance
        """
        thread = create_managed_thread(
            name=name,
            target=target,
            args=args or (),
            daemon=True,
            auto_start=True,
            cleanup_callback=lambda: logger.debug(f"Cleaned up {name} thread")
        )
        
        self.threads[name] = thread
        return thread
    
    def stop_all_threads(self) -> Dict[str, bool]:
        """
        Stop all managed threads.
        
        Returns:
            Dict[str, bool]: Dictionary mapping thread names to stop success status
        """
        results = {}
        
        for name, thread in list(self.threads.items()):
            try:
                if thread.is_alive():
                    thread.stop()
                    results[name] = True
                else:
                    results[name] = True
                    
                del self.threads[name]
            except Exception as e:
                logger.error(f"Error stopping thread {name}: {str(e)}")
                results[name] = False
        
        return results
    
    def is_thread_alive(self, name: str) -> bool:
        """
        Check if a thread is alive.
        
        Args:
            name: Thread name
            
        Returns:
            bool: True if thread is alive
        """
        return name in self.threads and self.threads[name].is_alive()
    
    def get_thread_stats(self) -> Dict[str, Any]:
        """
        Get statistics about managed threads.
        
        Returns:
            Dict: Thread statistics
        """
        stats = {
            "total_threads": len(self.threads),
            "active_threads": sum(1 for t in self.threads.values() if t.is_alive()),
            "threads": {}
        }
        
        for name, thread in self.threads.items():
            stats["threads"][name] = {
                "alive": thread.is_alive(),
                "daemon": thread.daemon,
                "ident": thread.ident
            }
        
        return stats
