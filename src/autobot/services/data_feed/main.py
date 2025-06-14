import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .config import DataFeedConfig
from .cache import RedisCache
from .connections import WebSocketManager

logging.basicConfig(
    level=getattr(logging, DataFeedConfig.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/data_feed.log')
    ]
)
logger = logging.getLogger('autobot.data_feed')

redis_cache = RedisCache()
websocket_manager = WebSocketManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AUTOBOT Data Feed Service")
    
    try:
        await redis_cache.connect()
        
        websocket_manager.cache_callback = redis_cache.store_tick
        
        await websocket_manager.initialize_exchanges()
        
        await websocket_manager.start_websocket_feeds()
        
        logger.info("Data Feed Service started successfully")
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to start Data Feed Service: {e}")
        raise
    finally:
        logger.info("Shutting down Data Feed Service")
        
        await websocket_manager.stop_websocket_feeds()
        
        await redis_cache.disconnect()
        
        logger.info("Data Feed Service shutdown complete")

app = FastAPI(
    title="AUTOBOT Data Feed Service",
    description="Real-time cryptocurrency data feed service using WebSockets",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    try:
        redis_health = await redis_cache.health_check()
        websocket_health = await websocket_manager.health_check()
        
        overall_status = "healthy"
        if redis_health.get("status") != "healthy" or websocket_health.get("status") not in ["healthy", "stopped"]:
            overall_status = "degraded"
        
        return {
            "status": overall_status,
            "service": "data_feed",
            "version": "1.0.0",
            "redis": redis_health,
            "websockets": websocket_health,
            "config": {
                "symbols": DataFeedConfig.SYMBOLS,
                "exchanges": DataFeedConfig.SUPPORTED_EXCHANGES,
                "tick_history_size": DataFeedConfig.TICK_HISTORY_SIZE
            }
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error",
            "service": "data_feed",
            "error": str(e)
        }

def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    sys.exit(0)

if __name__ == "__main__":
    import uvicorn
    import os
    
    os.makedirs('logs', exist_ok=True)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=DataFeedConfig.HEALTH_CHECK_PORT,
            log_level=DataFeedConfig.LOG_LEVEL.lower(),
            access_log=True
        )
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error(f"Service failed to start: {e}")
        sys.exit(1)
