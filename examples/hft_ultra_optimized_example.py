"""
Example of using the ultra-optimized HFT module for AUTOBOT.

This example demonstrates how to configure and use the ultra-optimized HFT module
to process hundreds of millions of orders per minute through advanced techniques
like NUMA optimization, memory preallocation, and message compression.
"""

import os
import logging
import time
from typing import Dict, Any

from autobot.trading.hft_ultra_optimized import (
    create_ultra_optimized_hft_engine,
    ProcessingMode
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """
    Main function demonstrating ultra-optimized HFT engine.
    """
    engine = create_ultra_optimized_hft_engine(
        batch_size=200_000,                # 200k orders per batch
        throttle_ns=25_000,                # 25μs throttle
        num_workers=None,                  # Auto-detect optimal worker count
        processing_mode="ULTRA",           # Use ultra mode for maximum performance
        enable_numa=True,                  # Enable NUMA optimization
        enable_gpu=True,                   # Enable GPU acceleration if available
        enable_compression=True,           # Enable message compression
        memory_pool_size=2_000_000_000     # 2GB memory pool
    )
    
    try:
        logger.info("Processing 10 batches of orders...")
        result = engine.process_orders(num_batches=10)
        
        logger.info(f"Processed {result['processed']} orders in {result['processing_time']:.6f} seconds")
        logger.info(f"Orders per second: {result['orders_per_second']:,}")
        
        stats = engine.get_stats()
        logger.info(f"Engine statistics: {stats}")
        
        logger.info("Processing orders continuously for 5 seconds...")
        start_time = time.time()
        total_processed = 0
        
        while time.time() - start_time < 5:
            result = engine.process_orders(num_batches=1)
            total_processed += result['processed']
            
            time.sleep(0.001)
        
        elapsed = time.time() - start_time
        orders_per_second = int(total_processed / elapsed)
        
        logger.info(f"Processed {total_processed:,} orders in {elapsed:.2f} seconds")
        logger.info(f"Orders per second: {orders_per_second:,}")
        logger.info(f"Orders per minute: {orders_per_second * 60:,}")
        
    finally:
        engine.shutdown()
        logger.info("Engine shutdown complete")

if __name__ == "__main__":
    main()
