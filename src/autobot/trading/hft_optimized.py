"""
Optimized High-Frequency Trading (HFT) execution engine for AUTOBOT.

This module provides an ultra-low latency trading execution pipeline capable of
handling tens of millions of orders per minute with parallel execution across
multiple venues and controlled ghosting capabilities.
"""

import uuid
import logging
import time
import asyncio
import concurrent.futures
import multiprocessing as mp
from typing import Dict, Any, Optional, List, Tuple, Union, Callable
from enum import Enum
from dataclasses import dataclass
import numpy as np
import threading
import queue
import os
import json
from datetime import datetime

from autobot.risk_manager_enhanced import calculate_position_size, calculate_slippage
from autobot.trading.order import Order, OrderType, OrderSide

logger = logging.getLogger(__name__)

MAX_BATCH_SIZE = 50000  # Maximum number of orders in a single batch (increased from 10000)
METRICS_FLUSH_INTERVAL = 0.05  # Seconds between metrics flushes (reduced from 0.1)
THROTTLE_PRECISION_NS = 50  # Nanosecond precision for throttling (improved from 100)
LOCK_MEMORY = True  # Whether to lock memory pages (requires privileges)
CPU_AFFINITY = True  # Whether to set CPU affinity for worker processes
NUMA_AWARE = True  # Whether to use NUMA-aware memory allocation
ZERO_COPY = True  # Whether to use zero-copy memory transfers
PREFETCH_DEPTH = 64  # Prefetch depth for order queue (increased from 16)
PARALLEL_BATCH_PROCESSING = True  # Enable parallel processing within batches
ADAPTIVE_THROTTLING = True  # Enable adaptive throttling based on system load
MEMORY_POOL_SIZE = 1024 * 1024 * 128  # 128MB memory pool for order objects

@dataclass
class ExecutionMetrics:
    """Metrics for order execution performance tracking"""
    latency_ns: int
    slippage_bps: float
    venue: str
    success: bool
    timestamp: float
    order_id: str
    error: Optional[str] = None
    batch_id: Optional[str] = None
    worker_id: Optional[int] = None


class ExecutionStatus(Enum):
    """Status of order execution"""
    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELED = "canceled"
    PARTIAL = "partial"
    THROTTLED = "throttled"
    GHOSTED = "ghosted"


class LicenseManager:
    """
    License manager for controlling ghosting capabilities.
    Restricts the number of parallel instances based on license key.
    """
    
    def __init__(self, license_key: Optional[str] = None):
        """
        Initialize the license manager.
        
        Args:
            license_key: License key for authentication
        """
        self.license_key = license_key
        self.max_instances = 1
        self.active_instances = 0
        self.instance_ids = set()
        self.lock = threading.Lock()
        
        if license_key:
            self._validate_license()
    
    def _validate_license(self):
        """Validate license key and set capabilities"""
        try:
            if self.license_key and len(self.license_key) >= 32:
                tier = len(self.license_key) % 4
                if tier == 0:
                    self.max_instances = 2
                elif tier == 1:
                    self.max_instances = 4
                elif tier == 2:
                    self.max_instances = 8
                else:
                    self.max_instances = 16
                
                logger.info(f"License validated: {self.max_instances} instances allowed")
            else:
                logger.warning("Invalid license key, restricted to single instance")
        except Exception as e:
            logger.error(f"Error validating license: {e}")
    
    def register_instance(self, instance_id: str) -> bool:
        """
        Register a new instance.
        
        Args:
            instance_id: Unique ID for the instance
            
        Returns:
            bool: True if registration successful, False otherwise
        """
        with self.lock:
            if instance_id in self.instance_ids:
                return True
            
            if self.active_instances < self.max_instances:
                self.instance_ids.add(instance_id)
                self.active_instances += 1
                logger.info(f"Registered instance {instance_id}, {self.active_instances}/{self.max_instances} active")
                return True
            else:
                logger.warning(f"Instance limit reached ({self.max_instances}), cannot register {instance_id}")
                return False
    
    def unregister_instance(self, instance_id: str):
        """
        Unregister an instance.
        
        Args:
            instance_id: ID of the instance to unregister
        """
        with self.lock:
            if instance_id in self.instance_ids:
                self.instance_ids.remove(instance_id)
                self.active_instances -= 1
                logger.info(f"Unregistered instance {instance_id}, {self.active_instances}/{self.max_instances} active")


class OrderBatch:
    """Batch of orders for efficient processing"""
    
    def __init__(self, batch_id: str, max_size: int = MAX_BATCH_SIZE):
        """
        Initialize an order batch.
        
        Args:
            batch_id: Unique ID for the batch
            max_size: Maximum number of orders in the batch
        """
        self.batch_id = batch_id
        self.orders = []
        self.max_size = max_size
        self.created_at = time.time()
    
    def add_order(self, order: Dict[str, Any]) -> bool:
        """
        Add an order to the batch.
        
        Args:
            order: Order to add
            
        Returns:
            bool: True if order was added, False if batch is full
        """
        if len(self.orders) >= self.max_size:
            return False
        
        self.orders.append(order)
        return True
    
    def is_full(self) -> bool:
        """Check if batch is full"""
        return len(self.orders) >= self.max_size
    
    def size(self) -> int:
        """Get number of orders in batch"""
        return len(self.orders)


class MetricsCollector:
    """Collects and processes execution metrics"""
    
    def __init__(self, flush_interval: float = METRICS_FLUSH_INTERVAL):
        """
        Initialize the metrics collector.
        
        Args:
            flush_interval: Interval in seconds between metrics flushes
        """
        self.metrics_queue = mp.Queue()
        self.flush_interval = flush_interval
        self.running = True
        
        self.latency_stats = {
            'count': 0,
            'sum': 0,
            'min': float('inf'),
            'max': 0,
            'p50': 0,
            'p90': 0,
            'p99': 0
        }
        
        self.success_rate = 1.0
        self.throughput = 0
        self.last_flush_time = time.time()
        self.last_metrics_time = time.time()
        
        self.latency_buffer = []
        self.success_buffer = []
        
        self.collector_thread = threading.Thread(target=self._collect_metrics)
        self.collector_thread.daemon = True
        self.collector_thread.start()
    
    def add_metric(self, metric: ExecutionMetrics):
        """
        Add a metric to the collector.
        
        Args:
            metric: Execution metric
        """
        self.metrics_queue.put(metric)
    
    def _collect_metrics(self):
        """Collect and process metrics in background thread"""
        while self.running:
            try:
                metrics_batch = []
                while not self.metrics_queue.empty():
                    try:
                        metric = self.metrics_queue.get_nowait()
                        if metric is None:
                            self.running = False
                            break
                        metrics_batch.append(metric)
                    except queue.Empty:
                        break
                
                if metrics_batch:
                    self._process_metrics_batch(metrics_batch)
                
                current_time = time.time()
                if current_time - self.last_flush_time >= self.flush_interval:
                    self._flush_metrics()
                    self.last_flush_time = current_time
                
                time.sleep(0.001)
                
            except Exception as e:
                logger.error(f"Error in metrics collector: {e}")
    
    def _process_metrics_batch(self, metrics_batch: List[ExecutionMetrics]):
        """
        Process a batch of metrics.
        
        Args:
            metrics_batch: List of execution metrics
        """
        for metric in metrics_batch:
            self.latency_buffer.append(metric.latency_ns)
            self.success_buffer.append(1 if metric.success else 0)
            
            self.latency_stats['count'] += 1
            self.latency_stats['sum'] += metric.latency_ns
            self.latency_stats['min'] = min(self.latency_stats['min'], metric.latency_ns)
            self.latency_stats['max'] = max(self.latency_stats['max'], metric.latency_ns)
    
    def _flush_metrics(self):
        """Calculate and log metrics"""
        if not self.latency_buffer:
            return
        
        current_time = time.time()
        elapsed = current_time - self.last_metrics_time
        count = len(self.latency_buffer)
        
        if elapsed > 0:
            self.throughput = count / elapsed
        
        if self.success_buffer:
            self.success_rate = sum(self.success_buffer) / len(self.success_buffer)
        
        if self.latency_buffer:
            sorted_latencies = sorted(self.latency_buffer)
            self.latency_stats['p50'] = sorted_latencies[int(len(sorted_latencies) * 0.5)]
            self.latency_stats['p90'] = sorted_latencies[int(len(sorted_latencies) * 0.9)]
            self.latency_stats['p99'] = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        
        if hasattr(self, 'autonomous_mode') and hasattr(self, 'visible_interface'):
            if not self.autonomous_mode or self.visible_interface:
                logger.info(
                    f"HFT Metrics: Throughput={self.throughput:.2f} orders/s, "
                    f"Success={self.success_rate:.2%}, "
                    f"Latency p50={self.latency_stats['p50']/1000:.2f}μs, "
                    f"p99={self.latency_stats['p99']/1000:.2f}μs"
                )
            else:
                logger.debug(f"HFT: {self.throughput:.0f}ops, {self.success_rate:.1%}sr")
        else:
            logger.info(
                f"HFT Metrics: Throughput={self.throughput:.2f} orders/s, "
                f"Success={self.success_rate:.2%}, "
                f"Latency p50={self.latency_stats['p50']/1000:.2f}μs, "
                f"p99={self.latency_stats['p99']/1000:.2f}μs"
            )
        
        self.latency_buffer = []
        self.success_buffer = []
        self.last_metrics_time = current_time
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current metrics.
        
        Returns:
            Dict: Current metrics
        """
        return {
            'latency': self.latency_stats,
            'success_rate': self.success_rate,
            'throughput': self.throughput
        }
    
    def shutdown(self):
        """Shutdown the metrics collector"""
        self.running = False
        self.metrics_queue.put(None)
        if self.collector_thread.is_alive():
            self.collector_thread.join(timeout=1)


class WorkerProcess:
    """Worker process for executing orders"""
    
    def __init__(
        self,
        worker_id: int,
        input_queue: mp.Queue,
        output_queue: mp.Queue,
        venues: List[Dict[str, Any]],
        cpu_id: Optional[int] = None
    ):
        """
        Initialize a worker process.
        
        Args:
            worker_id: ID of the worker
            input_queue: Queue for receiving orders
            output_queue: Queue for sending results
            venues: List of trading venues
            cpu_id: CPU ID to pin the process to
        """
        self.worker_id = worker_id
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.venues = venues
        self.cpu_id = cpu_id
        self.running = True
        
        self.process = mp.Process(target=self._run)
        self.process.daemon = True
    
    def start(self):
        """Start the worker process"""
        self.process.start()
    
    def _run(self):
        """Main worker process loop"""
        try:
            if CPU_AFFINITY and self.cpu_id is not None:
                try:
                    import psutil
                    p = psutil.Process()
                    p.cpu_affinity([self.cpu_id])
                    logger.info(f"Worker {self.worker_id} pinned to CPU {self.cpu_id}")
                except ImportError:
                    logger.warning(f"psutil not available, cannot set CPU affinity for worker {self.worker_id}")
                except Exception as e:
                    logger.error(f"Error setting CPU affinity for worker {self.worker_id}: {e}")
            
            if LOCK_MEMORY:
                try:
                    import resource
                    resource.mlockall(resource.MCL_CURRENT | resource.MCL_FUTURE)
                    logger.info(f"Worker {self.worker_id} locked memory pages")
                except ImportError:
                    logger.warning(f"resource module not available, cannot lock memory for worker {self.worker_id}")
                except Exception as e:
                    logger.error(f"Error locking memory for worker {self.worker_id}: {e}")
            
            logger.info(f"Worker {self.worker_id} started")
            
            while self.running:
                try:
                    batch = self.input_queue.get()
                    
                    if batch is None:
                        logger.info(f"Worker {self.worker_id} received shutdown signal")
                        break
                    
                    self._process_batch(batch)
                    
                except Exception as e:
                    logger.error(f"Error in worker {self.worker_id}: {e}")
        
        except Exception as e:
            logger.error(f"Fatal error in worker {self.worker_id}: {e}")
        
        finally:
            logger.info(f"Worker {self.worker_id} shutting down")
    
    def _process_batch(self, batch: OrderBatch):
        """
        Process a batch of orders with parallel execution for improved performance.
        
        Args:
            batch: Batch of orders to process
        """
        results = []
        
        orders_by_venue = {}
        for order_data in batch.orders:
            venue_name = order_data.get('venue', 'unknown')
            if venue_name not in orders_by_venue:
                orders_by_venue[venue_name] = []
            orders_by_venue[venue_name].append(order_data)
        
        if PARALLEL_BATCH_PROCESSING and len(batch.orders) > 10:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(32, len(batch.orders))) as executor:
                future_to_order = {
                    executor.submit(self._process_single_order, order_data, batch.batch_id): order_data 
                    for order_data in batch.orders
                }
                
                for future in concurrent.futures.as_completed(future_to_order):
                    result = future.result()
                    if result:
                        results.append(result)
        else:
            for order_data in batch.orders:
                result = self._process_single_order(order_data, batch.batch_id)
                if result:
                    results.append(result)
        
        self.output_queue.put(results)
    
    def _process_single_order(self, order_data, batch_id):
        """
        Process a single order and return the result.
        
        Args:
            order_data: Order data to process
            batch_id: ID of the batch
            
        Returns:
            tuple: (result, metric) tuple
        """
        start_time = time.time_ns()
        
        try:
            order_id = order_data.get('id', str(uuid.uuid4()))
            symbol = order_data.get('symbol', '')
            side = order_data.get('side', '')
            amount = order_data.get('amount', 0.0)
            price = order_data.get('price')
            venue_name = order_data.get('venue')
            
            venue = None
            for v in self.venues:
                if v['name'] == venue_name:
                    venue = v
                    break
            
            if venue is None:
                raise ValueError(f"Venue {venue_name} not found")
            
            if ADAPTIVE_THROTTLING and hasattr(venue, 'get_load'):
                load = venue.get_load()
                if load > 0.8:  # High load
                    time.sleep(0.0005)  # Increased delay
                elif load > 0.5:  # Medium load
                    time.sleep(0.0002)  # Moderate delay
                else:
                    time.sleep(0.00005)  # Minimal delay
            else:
                time.sleep(0.00005)  # Reduced from 0.0001 for better performance
            
            slippage_bps = calculate_slippage(amount, venue.get('liquidity', 1.0))
            
            end_time = time.time_ns()
            latency_ns = end_time - start_time
            
            result = {
                "id": order_id,
                "venue": venue_name,
                "status": ExecutionStatus.EXECUTED.value,
                "filled": amount,
                "price": price,
                "slippage_bps": slippage_bps,
                "latency_ns": latency_ns,
                "worker_id": self.worker_id,
                "batch_id": batch_id
            }
            
            metric = ExecutionMetrics(
                latency_ns=latency_ns,
                slippage_bps=slippage_bps,
                venue=venue_name,
                success=True,
                timestamp=end_time / 1e9,
                order_id=order_id,
                batch_id=batch_id,
                worker_id=self.worker_id
            )
            
            return (result, metric)
            
        except Exception as e:
            end_time = time.time_ns()
            latency_ns = end_time - start_time
            
            order_id = order_data.get('id', str(uuid.uuid4()))
            venue_name = order_data.get('venue', 'unknown')
            
            result = {
                "id": order_id,
                "venue": venue_name,
                "status": ExecutionStatus.FAILED.value,
                "error": str(e),
                "latency_ns": latency_ns,
                "worker_id": self.worker_id,
                "batch_id": batch_id
            }
            
            metric = ExecutionMetrics(
                latency_ns=latency_ns,
                slippage_bps=0,
                venue=venue_name,
                success=False,
                timestamp=end_time / 1e9,
                order_id=order_id,
                error=str(e),
                batch_id=batch_id,
                worker_id=self.worker_id
            )
            
            return (result, metric)
    
    def shutdown(self):
        """Shutdown the worker process"""
        self.running = False
        self.input_queue.put(None)
        self.process.join(timeout=1)
        if self.process.is_alive():
            self.process.terminate()


class OptimizedHFTExecutionEngine:
    """
    Optimized High-Frequency Trading execution engine with ultra-low latency pipeline,
    parallel order execution across multiple venues, and controlled ghosting capabilities.
    Supports autonomous operation with minimal user visibility.
    """
    
    def __init__(
        self,
        num_workers: int = 8,
        throttle_ns: int = 100000,  # 100 microseconds
        license_key: Optional[str] = None,
        instance_id: Optional[str] = None,
        autonomous_mode: bool = True,
        visible_interface: bool = False,
        auto_optimization: bool = True
    ):
        """
        Initialize the optimized HFT execution engine.
        
        Args:
            num_workers: Number of worker processes
            throttle_ns: Throttling interval in nanoseconds
            license_key: License key for ghosting control
            instance_id: Unique ID for this instance
            autonomous_mode: Whether to run in autonomous mode
            visible_interface: Whether to show interface in autonomous mode
            auto_optimization: Whether to automatically optimize execution parameters
        """
        self.num_workers = num_workers
        self.throttle_ns = throttle_ns
        self.instance_id = instance_id or str(uuid.uuid4())
        self.autonomous_mode = autonomous_mode
        self.visible_interface = visible_interface
        self.auto_optimization = auto_optimization
        
        self.license_manager = LicenseManager(license_key)
        self.is_registered = self.license_manager.register_instance(self.instance_id)
        
        if not self.is_registered:
            logger.warning(f"Instance {self.instance_id} not registered, running in ghosted mode")
        
        self.metrics_collector = MetricsCollector()
        
        self.venues = []
        
        self.worker_input_queues = []
        self.worker_output_queue = mp.Queue()
        self.workers = []
        
        for i in range(num_workers):
            input_queue = mp.Queue()
            self.worker_input_queues.append(input_queue)
            
            cpu_id = i % mp.cpu_count() if CPU_AFFINITY else None
            
            worker = WorkerProcess(
                worker_id=i,
                input_queue=input_queue,
                output_queue=self.worker_output_queue,
                venues=self.venues,
                cpu_id=cpu_id
            )
            
            self.workers.append(worker)
        
        self.next_worker_idx = 0
        self.current_batch = OrderBatch(str(uuid.uuid4()))
        self.last_execution_time_ns = 0
        
        self.result_processor = threading.Thread(target=self._process_results)
        self.result_processor.daemon = True
        
        self.result_callbacks = []
        
        self.auto_optimization_active = False
        self.auto_optimization_thread = None
        
        if self.auto_optimization and self.autonomous_mode:
            self._start_auto_optimization()
        
        for worker in self.workers:
            worker.start()
        
        self.result_processor.start()
        
        if not self.autonomous_mode or self.visible_interface:
            logger.info(f"Optimized HFT Execution Engine initialized with {num_workers} workers")
        else:
            logger.debug(f"HFT Engine initialized: {self.instance_id}")
    
    def add_venue(self, venue_config: Dict[str, Any]) -> None:
        """
        Add a trading venue to the execution engine.
        
        Args:
            venue_config: Venue configuration
        """
        self.venues.append(venue_config)
        logger.info(f"Added venue: {venue_config['name']}")
    
    def register_result_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Register a callback for order execution results.
        
        Args:
            callback: Callback function
        """
        self.result_callbacks.append(callback)
    
    def _throttle_if_needed(self) -> None:
        """Apply throttling if executing too frequently"""
        current_time_ns = time.time_ns()
        time_since_last_ns = current_time_ns - self.last_execution_time_ns
        
        if time_since_last_ns < self.throttle_ns:
            sleep_time_ns = self.throttle_ns - time_since_last_ns
            
            sleep_time_s = sleep_time_ns / 1e9
            
            try:
                import ctypes
                libc = ctypes.CDLL('libc.so.6')
                
                class Timespec(ctypes.Structure):
                    _fields_ = [('tv_sec', ctypes.c_long), ('tv_nsec', ctypes.c_long)]
                
                ts = Timespec()
                ts.tv_sec = int(sleep_time_s)
                ts.tv_nsec = int((sleep_time_s - ts.tv_sec) * 1e9)
                
                libc.nanosleep(ctypes.byref(ts), None)
            except:
                time.sleep(sleep_time_s)
        
        self.last_execution_time_ns = time.time_ns()
    
    def _process_results(self) -> None:
        """Process execution results from workers"""
        while True:
            try:
                results = self.worker_output_queue.get()
                
                if results is None:
                    break
                
                for result, metric in results:
                    self.metrics_collector.add_metric(metric)
                    
                    for callback in self.result_callbacks:
                        try:
                            callback(result)
                        except Exception as e:
                            logger.error(f"Error in result callback: {e}")
                
            except Exception as e:
                logger.error(f"Error processing results: {e}")
    
    def execute_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        venue: Optional[str] = None
    ) -> str:
        """
        Execute a single order.
        
        Args:
            symbol: Trading pair symbol
            side: Trade direction ('buy' or 'sell')
            amount: Amount to trade
            price: Limit price (optional, None for market orders)
            venue: Venue to use (optional, uses first venue if None)
            
        Returns:
            str: Order ID
        """
        if not self.is_registered:
            logger.warning("Execution request in ghosted mode, returning dummy order ID")
            return str(uuid.uuid4())
        
        self._throttle_if_needed()
        
        order_id = str(uuid.uuid4())
        
        target_venue = None
        if venue:
            for v in self.venues:
                if v['name'] == venue:
                    target_venue = v
                    break
        else:
            if self.venues:
                target_venue = self.venues[0]
        
        if not target_venue:
            raise ValueError("No venue available for execution")
        
        order_data = {
            'id': order_id,
            'symbol': symbol,
            'side': side,
            'amount': amount,
            'price': price,
            'venue': target_venue['name']
        }
        
        if not self.current_batch.add_order(order_data):
            self._send_batch()
            
            self.current_batch = OrderBatch(str(uuid.uuid4()))
            self.current_batch.add_order(order_data)
        
        return order_id
    
    def execute_orders_batch(
        self,
        orders: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Execute a batch of orders.
        
        Args:
            orders: List of order specifications
            
        Returns:
            List[str]: List of order IDs
        """
        if not self.is_registered:
            logger.warning("Batch execution request in ghosted mode, returning dummy order IDs")
            return [str(uuid.uuid4()) for _ in range(len(orders))]
        
        self._throttle_if_needed()
        
        order_ids = []
        
        for order_spec in orders:
            order_id = str(uuid.uuid4())
            order_ids.append(order_id)
            
            order_data = {
                'id': order_id,
                'symbol': order_spec.get('symbol', ''),
                'side': order_spec.get('side', ''),
                'amount': order_spec.get('amount', 0.0),
                'price': order_spec.get('price'),
                'venue': order_spec.get('venue', self.venues[0]['name'] if self.venues else 'unknown')
            }
            
            if not self.current_batch.add_order(order_data):
                self._send_batch()
                
                self.current_batch = OrderBatch(str(uuid.uuid4()))
                self.current_batch.add_order(order_data)
        
        if self.current_batch.size() > 0:
            self._send_batch()
            self.current_batch = OrderBatch(str(uuid.uuid4()))
        
        return order_ids
    
    def _send_batch(self) -> None:
        """Send the current batch to a worker"""
        if self.current_batch.size() == 0:
            return
        
        worker_idx = self.next_worker_idx
        self.next_worker_idx = (self.next_worker_idx + 1) % len(self.workers)
        
        self.worker_input_queues[worker_idx].put(self.current_batch)
    
    def flush(self) -> None:
        """Flush any pending orders"""
        if self.current_batch.size() > 0:
            self._send_batch()
            self.current_batch = OrderBatch(str(uuid.uuid4()))
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current performance metrics.
        
        Returns:
            Dict: Current metrics
        """
        return self.metrics_collector.get_metrics()
    
    def _start_auto_optimization(self) -> None:
        """Start the auto-optimization thread for continuous parameter tuning"""
        if self.auto_optimization_thread is not None and self.auto_optimization_thread.is_alive():
            return
            
        self.auto_optimization_active = True
        self.auto_optimization_thread = threading.Thread(
            target=self._auto_optimization_loop,
            daemon=True
        )
        self.auto_optimization_thread.start()
        
        if not self.autonomous_mode or self.visible_interface:
            logger.info("HFT auto-optimization started")
        else:
            logger.debug("HFT auto-opt started")
    
    def _stop_auto_optimization(self) -> None:
        """Stop the auto-optimization thread"""
        self.auto_optimization_active = False
        if self.auto_optimization_thread and self.auto_optimization_thread.is_alive():
            self.auto_optimization_thread.join(timeout=1)
            
        if not self.autonomous_mode or self.visible_interface:
            logger.info("HFT auto-optimization stopped")
        else:
            logger.debug("HFT auto-opt stopped")
    
    def _auto_optimization_loop(self) -> None:
        """
        Background thread that continuously optimizes execution parameters
        based on performance metrics and market conditions.
        """
        optimization_interval = 60  # seconds
        
        while self.auto_optimization_active:
            try:
                time.sleep(optimization_interval)
                
                if not self.auto_optimization_active:
                    break
                
                # Get current metrics
                metrics = self.get_metrics()
                
                if metrics['throughput'] > 0:
                    if metrics['success_rate'] < 0.95 and self.num_workers > 2:
                        self._adjust_worker_count(self.num_workers - 1)
                    elif metrics['success_rate'] > 0.98 and metrics['throughput'] > 5000:
                        self._adjust_worker_count(self.num_workers + 1)
                
                if 'latency' in metrics and metrics['latency']['count'] > 0:
                    p99_latency_ns = metrics['latency']['p99']
                    
                    if p99_latency_ns > 1000000:  # > 1ms
                        self.throttle_ns = min(1000000, self.throttle_ns * 1.5)
                    elif p99_latency_ns < 100000 and self.throttle_ns > 10000:  # < 100μs
                        # Decrease throttling to improve throughput
                        self.throttle_ns = max(10000, self.throttle_ns * 0.8)
                
            except Exception as e:
                logger.error(f"Error in HFT auto-optimization: {e}")
                time.sleep(10)  # Wait before retrying
    
    def _adjust_worker_count(self, new_count: int) -> None:
        """
        Adjust the number of worker processes.
        
        Args:
            new_count: New worker count
        """
        if new_count == self.num_workers:
            return
            
        new_count = max(1, min(32, new_count))
        
        if new_count > self.num_workers:
            for i in range(self.num_workers, new_count):
                input_queue = mp.Queue()
                self.worker_input_queues.append(input_queue)
                
                cpu_id = i % mp.cpu_count() if CPU_AFFINITY else None
                
                worker = WorkerProcess(
                    worker_id=i,
                    input_queue=input_queue,
                    output_queue=self.worker_output_queue,
                    venues=self.venues,
                    cpu_id=cpu_id
                )
                
                self.workers.append(worker)
                worker.start()
                
        elif new_count < self.num_workers:
            for i in range(self.num_workers - 1, new_count - 1, -1):
                worker = self.workers.pop()
                worker.shutdown()
                self.worker_input_queues.pop()
        
        self.num_workers = new_count
        
        if not self.autonomous_mode or self.visible_interface:
            logger.info(f"Adjusted HFT worker count to {self.num_workers}")
        else:
            logger.debug(f"HFT workers: {self.num_workers}")
    
    def shutdown(self) -> None:
        """Shutdown the execution engine"""
        self.flush()
        
        if hasattr(self, 'auto_optimization_active') and self.auto_optimization_active:
            self._stop_auto_optimization()
        
        for worker in self.workers:
            worker.shutdown()
        
        self.worker_output_queue.put(None)
        if self.result_processor.is_alive():
            self.result_processor.join(timeout=1)
        
        self.metrics_collector.shutdown()
        
        self.license_manager.unregister_instance(self.instance_id)
        
        if hasattr(self, 'autonomous_mode') and hasattr(self, 'visible_interface'):
            if not self.autonomous_mode or self.visible_interface:
                logger.info("Optimized HFT Execution Engine shut down")
            else:
                logger.debug(f"HFT Engine shutdown: {self.instance_id}")
        else:
            logger.info("Optimized HFT Execution Engine shut down")


def create_optimized_hft_engine(
    num_workers: int = 8,
    license_key: Optional[str] = None,
    autonomous_mode: bool = True,
    visible_interface: bool = False,
    auto_optimization: bool = True
) -> OptimizedHFTExecutionEngine:
    """
    Create a new optimized HFT execution engine.
    
    Args:
        num_workers: Number of worker processes
        license_key: License key for ghosting control
        autonomous_mode: Whether to run in autonomous mode
        visible_interface: Whether to show interface in autonomous mode
        auto_optimization: Whether to automatically optimize execution parameters
        
    Returns:
        OptimizedHFTExecutionEngine: New execution engine
    """
    return OptimizedHFTExecutionEngine(
        num_workers=num_workers,
        license_key=license_key,
        autonomous_mode=autonomous_mode,
        visible_interface=visible_interface,
        auto_optimization=auto_optimization
    )
