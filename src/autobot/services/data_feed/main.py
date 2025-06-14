import asyncio
import logging
import signal
import sys
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .config import DataFeedConfig
from .cache import RedisCache
from .connections import WebSocketManager

os.makedirs("logs", exist_ok=True)
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

app = FastAPI(
    title="AUTOBOT Data Feed Service",
    description="Real-time cryptocurrency data feed service using WebSockets",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting AUTOBOT Data Feed Service")
    
    try:
        logger.info(f"Connecting to Redis at {DataFeedConfig.REDIS_URL}")
        await redis_cache.connect()
        logger.info("✅ Redis connected successfully")
        
        app.state.redis = redis_cache.redis
        
        websocket_manager.cache_callback = redis_cache.store_tick
        await websocket_manager.initialize_exchanges()
        await websocket_manager.start_websocket_feeds()
        
        logger.info("Data Feed Service started successfully")
        
    except Exception as e:
        logger.error(f"❌ Failed to start Data Feed Service: {e}")
        logger.exception("Startup error details:")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Data Feed Service")
    
    try:
        await websocket_manager.stop_websocket_feeds()
        await redis_cache.disconnect()
        logger.info("Data Feed Service shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

@app.get("/health")
async def health():
    try:
        await app.state.redis.ping()
        logger.info("Redis ping OK")
        return {"status": "healthy"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse({"status": "degraded"}, status_code=503)

def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    sys.exit(0)

if __name__ == "__main__":
    import uvicorn
    import os
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        uvicorn.run(
            app,
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
