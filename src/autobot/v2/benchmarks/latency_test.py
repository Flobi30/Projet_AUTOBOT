"""
Latency Benchmark — Mesure la performance du hot path.
Cible : < 3ms de bout en bout.
"""

import asyncio
import time
import logging
import numpy as np
from datetime import datetime, timezone

from autobot.v2.websocket_async import TickerData

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Benchmark")

async def run_latency_test(orchestrator, pair="BTC/USD", iterations=1000):
    """
    Simule l'arrivée de ticks et mesure le temps de traitement jusqu'à
    la décision (hot path).
    """
    logger.info(f"🚀 Démarrage du benchmark de latence ({iterations} itérations)...")
    
    latencies = []
    
    # Mock ticker data
    price = 60000.0
    
    for i in range(iterations):
        price += np.random.normal(0, 10)
        ticker = TickerData(
            symbol=pair,
            price=price,
            bid=price - 0.5,
            ask=price + 0.5,
            volume_24h=1000.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        start = time.perf_counter()
        
        # Injection directe dans le dispatcher de l'orchestrateur (simule WS)
        # Note : On assume que l'orchestrateur a été initialisé
        if hasattr(orchestrator, "_ticker_callbacks"):
            callbacks = orchestrator._ticker_callbacks.get(pair, [])
            for cb in callbacks:
                await cb(ticker)
        
        end = time.perf_counter()
        latencies.append((end - start) * 1000) # ms
        
        if i % 100 == 0:
            logger.info(f"Progress: {i}/{iterations}")

    avg_lat = np.mean(latencies)
    p95_lat = np.percentile(latencies, 95)
    p99_lat = np.percentile(latencies, 99)
    
    logger.info(f"📊 Résultats du Benchmark (ms):")
    logger.info(f"   Moyenne : {avg_lat:.3f} ms")
    logger.info(f"   P95     : {p95_lat:.3f} ms")
    logger.info(f"   P99     : {p99_lat:.3f} ms")
    
    if p95_lat < 3.0:
        logger.info("✅ OBJECTIF ATTEINT : Latence < 3ms")
    else:
        logger.warning("⚠️ OBJECTIF NON ATTEINT : Latence > 3ms")

    return {
        "avg": avg_lat,
        "p95": p95_lat,
        "p99": p99_lat
    }

if __name__ == "__main__":
    # Test autonome minimal (nécessite l'environnement AutoBot complet)
    # python -m src.autobot.v2.benchmarks.latency_test
    pass
