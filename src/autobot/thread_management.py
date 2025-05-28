"""
Thread management module for AUTOBOT.

This module provides utilities for managing threads in AUTOBOT,
ensuring proper initialization, monitoring, and cleanup of threads
to prevent issues in CI and production environments.
"""

import threading
import logging
import time
import os
import signal
import atexit
import weakref
from typing import Dict, List, Set, Any, Optional, Callable

logger = logging.getLogger(__name__)

_thread_registry = weakref.WeakValueDictionary()
_thread_registry_lock = threading.Lock()

_shutdown_requested = False

class ManagedThread(threading.Thread):
    """
    A thread class that registers itself in the global registry.
    
    This class extends threading.Thread to provide automatic registration
    and cleanup capabilities, making it easier to manage threads in AUTOBOT.
    """
    
    def __init__(
        self,
        name: str = None,
        target: Callable = None,
        args: tuple = (),
        kwargs: dict = None,
        daemon: bool = True,
        auto_start: bool = False,
        cleanup_callback: Callable = None
    ):
        """
        Initialize a managed thread.
        
        Args:
            name: Name of the thread
            target: Target function to run
            args: Arguments to pass to the target function
            kwargs: Keyword arguments to pass to the target function
            daemon: Whether the thread is a daemon thread
            auto_start: Whether to automatically start the thread
            cleanup_callback: Callback to run when the thread is terminated
        """
        if kwargs is None:
            kwargs = {}
            
        super().__init__(
            name=name,
            target=self._wrapped_target,
            args=args,
            kwargs=kwargs,
            daemon=daemon
        )
        
        self._original_target = target
        self._cleanup_callback = cleanup_callback
        self._is_stopping = False
        
        with _thread_registry_lock:
            _thread_registry[self.name] = self
        
        if auto_start:
            self.start()
    
    def _wrapped_target(self, *args, **kwargs):
        """
        Wrap the target function to handle cleanup.
        
        This method wraps the target function to ensure proper cleanup
        when the thread is terminated.
        """
        try:
            if self._original_target:
                self._original_target(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in thread {self.name}: {str(e)}")
        finally:
            if self._cleanup_callback:
                try:
                    self._cleanup_callback()
                except Exception as e:
                    logger.error(f"Error in cleanup callback for thread {self.name}: {str(e)}")
    
    def stop(self, timeout: float = 2.0) -> bool:
        """
        Stop the thread.
        
        Args:
            timeout: Timeout in seconds to wait for the thread to stop
            
        Returns:
            bool: Whether the thread was stopped
        """
        if not self.is_alive():
            return True
        
        self._is_stopping = True
        
        self.join(timeout)
        
        if self.is_alive():
            if hasattr(self, "_stop"):
                self._stop()
            
            self.join(timeout)
        
        return not self.is_alive()

def register_thread(thread: threading.Thread) -> None:
    """
    Register a thread in the global registry.
    
    Args:
        thread: Thread to register
    """
    with _thread_registry_lock:
        _thread_registry[thread.name] = thread
        logger.debug(f"Registered thread: {thread.name}")

def unregister_thread(thread: threading.Thread) -> None:
    """
    Unregister a thread from the global registry.
    
    Args:
        thread: Thread to unregister
    """
    with _thread_registry_lock:
        if thread.name in _thread_registry:
            del _thread_registry[thread.name]
            logger.debug(f"Unregistered thread: {thread.name}")

def get_all_threads() -> Dict[str, threading.Thread]:
    """
    Get all registered threads.
    
    Returns:
        Dict: All registered threads
    """
    with _thread_registry_lock:
        return dict(_thread_registry)

def stop_all_threads(timeout: float = 2.0) -> Dict[str, bool]:
    """
    Stop all registered threads.
    
    Args:
        timeout: Timeout in seconds to wait for each thread to stop
        
    Returns:
        Dict: Results of stopping threads
    """
    global _shutdown_requested
    _shutdown_requested = True
    
    results = {}
    
    with _thread_registry_lock:
        threads = list(_thread_registry.items())
    
    for name, thread in threads:
        if isinstance(thread, ManagedThread):
            results[name] = thread.stop(timeout)
        elif hasattr(thread, "_stop"):
            try:
                thread._stop()
                thread.join(timeout)
                results[name] = not thread.is_alive()
            except Exception:
                results[name] = False
    
    return results

def is_shutdown_requested() -> bool:
    """
    Check if shutdown has been requested.
    
    Returns:
        bool: Whether shutdown has been requested
    """
    return _shutdown_requested

def create_managed_thread(
    name: str = None,
    target: Callable = None,
    args: tuple = (),
    kwargs: dict = None,
    daemon: bool = True,
    auto_start: bool = False,
    cleanup_callback: Callable = None
) -> ManagedThread:
    """
    Create and return a managed thread.
    
    Args:
        name: Name of the thread
        target: Target function to run
        args: Arguments to pass to the target function
        kwargs: Keyword arguments to pass to the target function
        daemon: Whether the thread is a daemon thread
        auto_start: Whether to automatically start the thread
        cleanup_callback: Callback to run when the thread is terminated
        
    Returns:
        ManagedThread: New managed thread instance
    """
    return ManagedThread(
        name=name,
        target=target,
        args=args,
        kwargs=kwargs,
        daemon=daemon,
        auto_start=auto_start,
        cleanup_callback=cleanup_callback
    )

@atexit.register
def _cleanup_threads():
    """Clean up threads when the program exits."""
    stop_all_threads()

def _signal_handler(signum, frame):
    """Handle signals to clean up threads."""
    stop_all_threads()
    
    if signum != signal.SIGINT:
        original_handler = signal.getsignal(signum)
        if callable(original_handler) and original_handler != _signal_handler:
            original_handler(signum, frame)

if not os.environ.get("PYTEST_CURRENT_TEST"):
    for sig in [signal.SIGTERM, signal.SIGINT]:
        try:
            signal.signal(sig, _signal_handler)
        except (ValueError, OSError):
            pass  # Signal not supported on this platform
