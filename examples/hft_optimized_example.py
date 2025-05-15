"""
Example of using the enhanced HFT module for high-performance trading.

This example demonstrates how to configure and use the enhanced HFT module
to process tens of millions of orders per minute through parallel batch
processing and adaptive throttling.
"""

import os
import time
import logging
import random
from typing import Dict, List, Any

from autobot.trading.hft_optimized_enhanced import create_hft_engine

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def generate_random_order(venue: str) -> Dict[str, Any]:
    """
    Generate a random order for testing.
    
    Args:
        venue: Trading venue
        
    Returns:
        Dict: Random order
    """
    symbols = ["BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD", "DOT/USD"]
    sides = ["buy", "sell"]
    order_types = ["limit", "market"]
    
    return {
        "venue": venue,
        "symbol": random.choice(symbols),
        "side": random.choice(sides),
        "type": random.choice(order_types),
        "amount": round(random.uniform(0.1, 10.0), 4),
        "price": round(random.uniform(10000, 50000), 2) if random.choice(sides) == "limit" else None,
        "params": {
            "leverage": random.randint(1, 10),
            "reduceOnly": random.choice([True, False]),
            "postOnly": random.choice([True, False])
        }
    }

def main():
    """
    Main function demonstrating enhanced HFT module usage.
    """
    # Create HFT engine with optimized parameters
    hft_engine = create_hft_engine(
        batch_size=50000,          # Process 50,000 orders per batch
        max_workers=16,            # Use 16 worker threads
        prefetch_depth=5,          # Prefetch 5 batches
        artificial_latency=0.00005, # 50 microseconds latency
        memory_pool_size=1000000,  # 1 million order objects in memory pool
        adaptive_throttling=True   # Use adaptive throttling
    )
    
    # Start the HFT engine
    hft_engine.start()
    
    try:
        # Generate and submit orders for multiple venues
        venues = ["binance", "coinbase", "kraken", "ftx", "bybit"]
        total_orders = 0
        
        logger.info("Starting order submission...")
        start_time = time.time()
        
        # Submit orders for 10 seconds
        while time.time() - start_time < 10:
            # Generate batch of orders for each venue
            for venue in venues:
                orders = [generate_random_order(venue) for _ in range(1000)]
                submitted = hft_engine.submit_orders(orders)
                total_orders += submitted
            
            # Small sleep to prevent CPU spinning
            time.sleep(0.001)
        
        elapsed = time.time() - start_time
        orders_per_second = total_orders / elapsed
        orders_per_minute = orders_per_second * 60
        
        logger.info(f"Submitted {total_orders} orders in {elapsed:.2f} seconds")
        logger.info(f"Performance: {orders_per_second:.2f} orders/s ({orders_per_minute:.2f} orders/min)")
        
        # Get engine metrics
        metrics = hft_engine.get_metrics()
        logger.info(f"Engine metrics: {metrics}")
        
        # Wait for processing to complete
        logger.info("Waiting for processing to complete...")
        time.sleep(5)
        
        # Get final metrics
        final_metrics = hft_engine.get_metrics()
        logger.info(f"Final metrics: {final_metrics}")
        
    finally:
        # Stop the HFT engine
        hft_engine.stop()
        logger.info("HFT engine stopped")

if __name__ == "__main__":
    main()
