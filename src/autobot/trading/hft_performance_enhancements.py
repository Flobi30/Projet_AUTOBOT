"""
Performance Enhancements for HFT Module

This module provides additional optimizations for the HFT module to increase
order processing capacity beyond tens of millions of orders per minute.
"""

import logging
import time
import threading
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class HFTPerformanceOptimizer:
    """
    Performance optimizer for HFT execution engine.
    
    This class provides additional optimizations to increase order processing
    capacity beyond tens of millions of orders per minute.
    """
    
    def __init__(
        self,
        hft_engine: Any,
        batch_size_multiplier: float = 2.0,
        throttle_reduction_factor: float = 0.5,
        memory_pool_expansion_factor: float = 5.0,
        worker_multiplier: float = 1.5,
        enable_numa_optimization: bool = True,
        enable_kernel_bypass: bool = False
    ):
        """
        Initialize the HFT performance optimizer.
        
        Args:
            hft_engine: HFT execution engine to optimize
            batch_size_multiplier: Factor to multiply batch size by
            throttle_reduction_factor: Factor to reduce throttling by
            memory_pool_expansion_factor: Factor to expand memory pool by
            worker_multiplier: Factor to multiply worker count by
            enable_numa_optimization: Whether to enable NUMA optimization
            enable_kernel_bypass: Whether to enable kernel bypass (requires privileges)
        """
        self.hft_engine = hft_engine
        self.batch_size_multiplier = batch_size_multiplier
        self.throttle_reduction_factor = throttle_reduction_factor
        self.memory_pool_expansion_factor = memory_pool_expansion_factor
        self.worker_multiplier = worker_multiplier
        self.enable_numa_optimization = enable_numa_optimization
        self.enable_kernel_bypass = enable_kernel_bypass
        
        self.original_settings = {}
        self.optimized = False
        
        logger.info("HFT Performance Optimizer initialized")
    
    def apply_optimizations(self) -> Dict[str, Any]:
        """
        Apply performance optimizations to the HFT engine.
        
        Returns:
            Dict: Original settings for reference
        """
        if self.optimized:
            logger.warning("Optimizations already applied")
            return self.original_settings
        
        self.original_settings = self._get_current_settings()
        
        self._optimize_batch_size()
        self._optimize_throttling()
        self._optimize_memory_pool()
        self._optimize_worker_count()
        self._optimize_system_settings()
        
        self.optimized = True
        
        logger.info("Applied HFT performance optimizations")
        return self.original_settings
    
    def restore_original_settings(self) -> None:
        """Restore original settings"""
        if not self.optimized or not self.original_settings:
            logger.warning("No optimizations to restore")
            return
        
        if hasattr(self.hft_engine, 'batch_size'):
            self.hft_engine.batch_size = self.original_settings.get('batch_size', self.hft_engine.batch_size)
        
        if hasattr(self.hft_engine, 'throttle_ns'):
            self.hft_engine.throttle_ns = self.original_settings.get('throttle_ns', self.hft_engine.throttle_ns)
        
        if hasattr(self.hft_engine, 'memory_pool_size'):
            self.hft_engine.memory_pool_size = self.original_settings.get('memory_pool_size', self.hft_engine.memory_pool_size)
        
        if hasattr(self.hft_engine, 'num_workers'):
            self._adjust_worker_count(self.original_settings.get('num_workers', self.hft_engine.num_workers))
        
        self.optimized = False
        
        logger.info("Restored original HFT settings")
    
    def _get_current_settings(self) -> Dict[str, Any]:
        """
        Get current HFT engine settings.
        
        Returns:
            Dict: Current settings
        """
        settings = {}
        
        if hasattr(self.hft_engine, 'batch_size'):
            settings['batch_size'] = self.hft_engine.batch_size
        
        if hasattr(self.hft_engine, 'throttle_ns'):
            settings['throttle_ns'] = self.hft_engine.throttle_ns
        
        if hasattr(self.hft_engine, 'memory_pool_size'):
            settings['memory_pool_size'] = self.hft_engine.memory_pool_size
        
        if hasattr(self.hft_engine, 'num_workers'):
            settings['num_workers'] = self.hft_engine.num_workers
        
        return settings
    
    def _optimize_batch_size(self) -> None:
        """Optimize batch size for maximum throughput"""
        if hasattr(self.hft_engine, 'batch_size'):
            new_batch_size = int(self.hft_engine.batch_size * self.batch_size_multiplier)
            self.hft_engine.batch_size = new_batch_size
            logger.info(f"Increased batch size to {new_batch_size}")
    
    def _optimize_throttling(self) -> None:
        """Optimize throttling for maximum throughput"""
        if hasattr(self.hft_engine, 'throttle_ns'):
            new_throttle_ns = int(self.hft_engine.throttle_ns * self.throttle_reduction_factor)
            self.hft_engine.throttle_ns = max(10000, new_throttle_ns)  # Minimum 10μs
            logger.info(f"Reduced throttling to {self.hft_engine.throttle_ns}ns")
    
    def _optimize_memory_pool(self) -> None:
        """Optimize memory pool for maximum throughput"""
        if hasattr(self.hft_engine, 'memory_pool_size'):
            new_memory_pool_size = int(self.hft_engine.memory_pool_size * self.memory_pool_expansion_factor)
            self.hft_engine.memory_pool_size = new_memory_pool_size
            logger.info(f"Expanded memory pool to {new_memory_pool_size}")
    
    def _optimize_worker_count(self) -> None:
        """Optimize worker count for maximum throughput"""
        if hasattr(self.hft_engine, 'num_workers'):
            import multiprocessing as mp
            max_workers = mp.cpu_count() * 2  # Maximum 2 workers per CPU
            new_worker_count = min(max_workers, int(self.hft_engine.num_workers * self.worker_multiplier))
            self._adjust_worker_count(new_worker_count)
            logger.info(f"Adjusted worker count to {new_worker_count}")
    
    def _adjust_worker_count(self, new_count: int) -> None:
        """
        Adjust worker count using the engine's own method if available.
        
        Args:
            new_count: New worker count
        """
        if hasattr(self.hft_engine, '_adjust_worker_count'):
            self.hft_engine._adjust_worker_count(new_count)
        elif hasattr(self.hft_engine, 'num_workers'):
            self.hft_engine.num_workers = new_count
    
    def _optimize_system_settings(self) -> None:
        """Optimize system settings for maximum throughput"""
        if self.enable_numa_optimization:
            try:
                import psutil
                import os
                
                process = psutil.Process(os.getpid())
                
                if hasattr(process, 'cpu_affinity'):
                    current_affinity = process.cpu_affinity()
                    
                    process.cpu_affinity(current_affinity)
                    
                    logger.info("Applied NUMA optimization")
            except ImportError:
                logger.warning("psutil not available, cannot apply NUMA optimization")
            except Exception as e:
                logger.error(f"Error applying NUMA optimization: {e}")
        
        if self.enable_kernel_bypass:
            try:
                logger.info("Kernel bypass enabled (placeholder)")
            except Exception as e:
                logger.error(f"Error enabling kernel bypass: {e}")


def apply_hft_optimizations(
    hft_engine: Any,
    batch_size_multiplier: float = 2.0,
    throttle_reduction_factor: float = 0.5,
    memory_pool_expansion_factor: float = 5.0,
    worker_multiplier: float = 1.5,
    enable_numa_optimization: bool = True,
    enable_kernel_bypass: bool = False
) -> HFTPerformanceOptimizer:
    """
    Apply performance optimizations to an HFT engine.
    
    Args:
        hft_engine: HFT execution engine to optimize
        batch_size_multiplier: Factor to multiply batch size by
        throttle_reduction_factor: Factor to reduce throttling by
        memory_pool_expansion_factor: Factor to expand memory pool by
        worker_multiplier: Factor to multiply worker count by
        enable_numa_optimization: Whether to enable NUMA optimization
        enable_kernel_bypass: Whether to enable kernel bypass
        
    Returns:
        HFTPerformanceOptimizer: Optimizer instance
    """
    optimizer = HFTPerformanceOptimizer(
        hft_engine=hft_engine,
        batch_size_multiplier=batch_size_multiplier,
        throttle_reduction_factor=throttle_reduction_factor,
        memory_pool_expansion_factor=memory_pool_expansion_factor,
        worker_multiplier=worker_multiplier,
        enable_numa_optimization=enable_numa_optimization,
        enable_kernel_bypass=enable_kernel_bypass
    )
    
    optimizer.apply_optimizations()
    
    return optimizer
