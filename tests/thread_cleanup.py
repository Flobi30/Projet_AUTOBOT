"""
Thread cleanup module for tests.

This module provides a pytest fixture to ensure all threads are properly terminated
after tests complete, preventing segmentation faults in CI.
"""

import threading
import pytest
import atexit
import signal
import os
import logging
import time
import sys
from typing import List, Dict, Any, Set

logger = logging.getLogger(__name__)

try:
    from autobot.thread_management import (
        stop_all_threads,
        get_all_threads,
        is_shutdown_requested
    )
    _has_thread_management = True
except ImportError:
    _has_thread_management = False
    logger.warning("Could not import thread_management module, falling back to basic thread cleanup")

_original_threads: Set[int] = set()
_monitored_threads: Dict[int, threading.Thread] = {}
_cleanup_lock = threading.Lock()

def _save_original_threads():
    """Save the IDs of threads that exist before tests start."""
    global _original_threads
    _original_threads = {t.ident for t in threading.enumerate() if t.ident is not None}
    logger.debug(f"Original threads: {_original_threads}")

def _monitor_new_threads():
    """Monitor for new threads and track them."""
    with _cleanup_lock:
        current_threads = threading.enumerate()
        for thread in current_threads:
            if thread.ident is not None and thread.ident not in _original_threads and thread.ident not in _monitored_threads:
                _monitored_threads[thread.ident] = thread
                logger.debug(f"Monitoring new thread: {thread.name} (ID: {thread.ident})")

def _terminate_threads():
    """Terminate all non-original threads."""
    logger.debug("Terminating threads...")
    
    if _has_thread_management:
        logger.debug("Using thread management module to stop threads")
        results = stop_all_threads(timeout=1.0)
        logger.debug(f"Thread stop results: {results}")
        return
    
    for module_name in [
        "autobot.rl.train", 
        "autobot.agents.superagi_integration_enhanced",
        "autobot.trading.mode_manager",
        "autobot.trading.cross_chain_arbitrage",
        "autobot.trading.institutional_flow_analyzer",
        "autobot.trading.oracle_integration",
        "autobot.trading.auto_hedging",
        "autobot.trading.market_meta_analysis"
    ]:
        try:
            module = __import__(module_name, fromlist=["*"])
            for flag_name in [
                "_auto_training_active",
                "_scanning_active", 
                "_monitoring_active", 
                "_autonomous_active",
                "_meta_analysis_active"
            ]:
                if hasattr(module, flag_name):
                    setattr(module, flag_name, False)
                    logger.debug(f"Set {module_name}.{flag_name} to False")
        except (ImportError, AttributeError) as e:
            logger.debug(f"Could not access module {module_name}: {e}")
    
    time.sleep(0.5)
    
    with _cleanup_lock:
        current_threads = threading.enumerate()
        for thread in current_threads:
            if (thread.ident is not None and 
                thread.ident not in _original_threads and 
                thread.is_alive() and 
                thread != threading.current_thread()):
                
                logger.debug(f"Forcefully terminating thread: {thread.name} (ID: {thread.ident})")
                
                if hasattr(thread, "_stop"):
                    thread._stop()

@pytest.fixture(scope="session", autouse=True)
def thread_cleanup():
    """
    Pytest fixture to ensure all threads are properly terminated after tests.
    
    This fixture runs automatically for all tests and helps prevent segmentation
    faults in CI by ensuring no zombie threads remain after test completion.
    """
    _save_original_threads()
    
    atexit.register(_terminate_threads)
    
    if not _has_thread_management:
        monitor_thread = threading.Thread(
            target=lambda: (
                [_monitor_new_threads(), time.sleep(1)] 
                for _ in range(60)  # Monitor for 60 seconds max
            ),
            daemon=True
        )
        monitor_thread.start()
    
    yield
    
    _terminate_threads()
