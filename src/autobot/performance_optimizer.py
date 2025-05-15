"""
Performance optimizer for AUTOBOT.

This module provides utilities to optimize the performance of AUTOBOT
by reducing memory usage, optimizing CPU utilization, and improving
overall system responsiveness.
"""

import gc
import os
import psutil
import threading
import logging
import time
from typing import Dict, Any, List, Optional, Callable
import numpy as np
import weakref

logger = logging.getLogger(__name__)

class PerformanceOptimizer:
    """
    Performance optimizer for AUTOBOT.
    
    This class provides utilities to optimize the performance of AUTOBOT
    by monitoring and managing system resources.
    """
    
    def __init__(
        self,
        memory_threshold: float = 0.85,
        cpu_threshold: float = 0.90,
        check_interval: float = 5.0,
        auto_optimize: bool = True,
        visible_interface: bool = True
    ):
        """
        Initialize the performance optimizer.
        
        Args:
            memory_threshold: Memory usage threshold (0.0-1.0) to trigger optimization
            cpu_threshold: CPU usage threshold (0.0-1.0) to trigger optimization
            check_interval: Interval in seconds between resource checks
            auto_optimize: Whether to automatically optimize performance
            visible_interface: Whether to show optimization messages in the interface
        """
        self.memory_threshold = memory_threshold
        self.cpu_threshold = cpu_threshold
        self.check_interval = check_interval
        self.auto_optimize = auto_optimize
        self.visible_interface = visible_interface
        
        self._monitoring_active = False
        self._monitoring_thread = None
        self._optimizers = []
        self._resource_stats = {
            "memory_usage": [],
            "cpu_usage": [],
            "thread_count": [],
            "optimization_events": []
        }
        
        self.register_optimizer(self._optimize_memory, "memory")
        self.register_optimizer(self._optimize_threads, "threads")
        self.register_optimizer(self._optimize_garbage_collection, "gc")
        
        if auto_optimize:
            self.start_monitoring()
    
    def register_optimizer(self, optimizer_func: Callable, name: str) -> None:
        """
        Register a new optimizer function.
        
        Args:
            optimizer_func: Function to call for optimization
            name: Name of the optimizer for logging
        """
        self._optimizers.append({
            "func": optimizer_func,
            "name": name,
            "last_run": 0
        })
        
        if self.visible_interface:
            logger.info(f"Registered optimizer: {name}")
        else:
            logger.debug(f"Registered optimizer: {name}")
    
    def start_monitoring(self) -> None:
        """Start the resource monitoring thread."""
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
                logger.info("Started performance monitoring")
            else:
                logger.debug("Started performance monitoring")
    
    def stop_monitoring(self) -> None:
        """Stop the resource monitoring thread."""
        self._monitoring_active = False
        
        if self.visible_interface:
            logger.info("Stopped performance monitoring")
        else:
            logger.debug("Stopped performance monitoring")
    
    def _monitoring_loop(self) -> None:
        """Background loop for monitoring system resources."""
        process = psutil.Process(os.getpid())
        
        while self._monitoring_active:
            try:
                memory_percent = process.memory_percent() / 100.0
                cpu_percent = process.cpu_percent() / 100.0
                thread_count = threading.active_count()
                
                self._resource_stats["memory_usage"].append(memory_percent)
                self._resource_stats["cpu_usage"].append(cpu_percent)
                self._resource_stats["thread_count"].append(thread_count)
                
                for key in ["memory_usage", "cpu_usage", "thread_count"]:
                    if len(self._resource_stats[key]) > 100:
                        self._resource_stats[key] = self._resource_stats[key][-100:]
                
                if memory_percent > self.memory_threshold or cpu_percent > self.cpu_threshold:
                    self._run_optimizers()
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in performance monitoring: {str(e)}")
                time.sleep(self.check_interval)
    
    def _run_optimizers(self) -> None:
        """Run all registered optimizers."""
        current_time = time.time()
        
        for optimizer in self._optimizers:
            if current_time - optimizer["last_run"] < 30:
                continue
                
            try:
                result = optimizer["func"]()
                optimizer["last_run"] = current_time
                
                if result:
                    self._resource_stats["optimization_events"].append({
                        "time": current_time,
                        "optimizer": optimizer["name"],
                        "result": result
                    })
                    
                    if self.visible_interface:
                        logger.info(f"Optimization ({optimizer['name']}): {result}")
                    else:
                        logger.debug(f"Optimization ({optimizer['name']}): {result}")
                    
            except Exception as e:
                logger.error(f"Error in optimizer {optimizer['name']}: {str(e)}")
    
    def _optimize_memory(self) -> Dict[str, Any]:
        """
        Optimize memory usage by clearing caches and releasing unused memory.
        
        Returns:
            Dict: Optimization results
        """
        before_memory = psutil.Process(os.getpid()).memory_percent() / 100.0
        
        if hasattr(np, "clear_cache"):
            np.clear_cache()
        
        gc.collect()
        
        if hasattr(psutil, "Process"):
            try:
                process = psutil.Process(os.getpid())
                if hasattr(process, "memory_maps"):
                    process.memory_maps()
            except Exception:
                pass
        
        after_memory = psutil.Process(os.getpid()).memory_percent() / 100.0
        memory_reduction = before_memory - after_memory
        
        return {
            "before_memory_percent": round(before_memory * 100, 2),
            "after_memory_percent": round(after_memory * 100, 2),
            "reduction_percent": round(memory_reduction * 100, 2)
        }
    
    def _optimize_threads(self) -> Dict[str, Any]:
        """
        Optimize thread usage by identifying and terminating zombie threads.
        
        Returns:
            Dict: Optimization results
        """
        before_count = threading.active_count()
        terminated_count = 0
        
        all_threads = threading.enumerate()
        
        for thread in all_threads:
            if thread.daemon and thread != threading.current_thread() and thread != self._monitoring_thread:
                if any(pattern in thread.name.lower() for pattern in ["worker", "temp", "pool", "scan", "monitor"]):
                    if hasattr(thread, "_stop"):
                        try:
                            thread._stop()
                            terminated_count += 1
                        except Exception:
                            pass
        
        after_count = threading.active_count()
        
        return {
            "before_thread_count": before_count,
            "after_thread_count": after_count,
            "terminated_count": terminated_count
        }
    
    def _optimize_garbage_collection(self) -> Dict[str, Any]:
        """
        Optimize garbage collection by running a full collection.
        
        Returns:
            Dict: Optimization results
        """
        before_counts = gc.get_count()
        
        gc_enabled = gc.isenabled()
        if gc_enabled:
            gc.disable()
        
        collected = gc.collect(2)
        
        if gc_enabled:
            gc.enable()
        
        after_counts = gc.get_count()
        
        return {
            "before_counts": before_counts,
            "after_counts": after_counts,
            "collected_objects": collected
        }
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics.
        
        Returns:
            Dict: Performance statistics
        """
        if not self._resource_stats["memory_usage"]:
            return {
                "memory_percent": 0,
                "cpu_percent": 0,
                "thread_count": threading.active_count(),
                "optimization_count": 0
            }
        
        return {
            "memory_percent": round(self._resource_stats["memory_usage"][-1] * 100, 2),
            "cpu_percent": round(self._resource_stats["cpu_usage"][-1] * 100, 2),
            "thread_count": self._resource_stats["thread_count"][-1],
            "optimization_count": len(self._resource_stats["optimization_events"]),
            "memory_trend": self._calculate_trend(self._resource_stats["memory_usage"]),
            "cpu_trend": self._calculate_trend(self._resource_stats["cpu_usage"]),
            "thread_trend": self._calculate_trend(self._resource_stats["thread_count"])
        }
    
    def _calculate_trend(self, values: List[float]) -> str:
        """
        Calculate the trend of a series of values.
        
        Args:
            values: List of values to analyze
            
        Returns:
            str: Trend direction ("up", "down", or "stable")
        """
        if len(values) < 5:
            return "stable"
        
        recent = values[-5:]
        
        x = np.arange(len(recent))
        y = np.array(recent)
        slope = np.polyfit(x, y, 1)[0]
        
        if slope > 0.01:
            return "up"
        elif slope < -0.01:
            return "down"
        else:
            return "stable"

def optimize_performance(
    memory_threshold: float = 0.85,
    cpu_threshold: float = 0.90,
    auto_optimize: bool = True,
    visible_interface: bool = True
) -> PerformanceOptimizer:
    """
    Create and return a performance optimizer.
    
    Args:
        memory_threshold: Memory usage threshold (0.0-1.0) to trigger optimization
        cpu_threshold: CPU usage threshold (0.0-1.0) to trigger optimization
        auto_optimize: Whether to automatically optimize performance
        visible_interface: Whether to show optimization messages in the interface
        
    Returns:
        PerformanceOptimizer: New performance optimizer instance
    """
    return PerformanceOptimizer(
        memory_threshold=memory_threshold,
        cpu_threshold=cpu_threshold,
        auto_optimize=auto_optimize,
        visible_interface=visible_interface
    )
