import asyncio
import logging
from typing import Dict, Any, Optional, Callable, List
import ccxt.pro as ccxt
from .config import DataFeedConfig

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self, cache_callback: Callable[[str, Dict[str, Any]], None] = None):
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.cache_callback = cache_callback
        self.symbols = DataFeedConfig.SYMBOLS
        self.running = False
        self.tasks: List[asyncio.Task] = []
        
    async def initialize_exchanges(self):
        for exchange_id in DataFeedConfig.SUPPORTED_EXCHANGES:
            try:
                config = DataFeedConfig.EXCHANGE_CONFIGS[exchange_id]
                
                exchange_class = getattr(ccxt, exchange_id)
                exchange = exchange_class(config)
                
                await exchange.load_markets()
                self.exchanges[exchange_id] = exchange
                
                logger.info(f"Initialized {exchange_id} exchange")
                
            except Exception as e:
                logger.error(f"Failed to initialize {exchange_id} exchange: {e}")
    
    async def start_websocket_feeds(self):
        self.running = True
        
        for exchange_id, exchange in self.exchanges.items():
            for symbol in self.symbols:
                try:
                    if symbol in exchange.markets:
                        task = asyncio.create_task(
                            self._watch_ticker(exchange_id, exchange, symbol)
                        )
                        self.tasks.append(task)
                        logger.info(f"Started WebSocket feed for {symbol} on {exchange_id}")
                    else:
                        logger.warning(f"Symbol {symbol} not available on {exchange_id}")
                        
                except Exception as e:
                    logger.error(f"Failed to start WebSocket for {symbol} on {exchange_id}: {e}")
    
    async def _watch_ticker(self, exchange_id: str, exchange: ccxt.Exchange, symbol: str):
        reconnect_attempts = 0
        max_attempts = DataFeedConfig.MAX_RECONNECT_ATTEMPTS
        
        while self.running and reconnect_attempts < max_attempts:
            try:
                logger.info(f"Starting ticker watch for {symbol} on {exchange_id}")
                
                while self.running:
                    try:
                        ticker = await exchange.watch_ticker(symbol)
                        
                        if ticker and self.cache_callback:
                            ticker_data = {
                                **ticker,
                                "exchange": exchange_id,
                                "symbol": symbol
                            }
                            await self.cache_callback(symbol, ticker_data)
                        
                        reconnect_attempts = 0
                        
                    except Exception as e:
                        logger.error(f"Error watching ticker {symbol} on {exchange_id}: {e}")
                        break
                        
            except Exception as e:
                reconnect_attempts += 1
                logger.error(
                    f"WebSocket connection failed for {symbol} on {exchange_id} "
                    f"(attempt {reconnect_attempts}/{max_attempts}): {e}"
                )
                
                if reconnect_attempts < max_attempts:
                    await asyncio.sleep(DataFeedConfig.WEBSOCKET_RECONNECT_DELAY)
                else:
                    logger.error(f"Max reconnection attempts reached for {symbol} on {exchange_id}")
                    break
    
    async def stop_websocket_feeds(self):
        self.running = False
        
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        for exchange_id, exchange in self.exchanges.items():
            try:
                await exchange.close()
                logger.info(f"Closed {exchange_id} exchange connection")
            except Exception as e:
                logger.error(f"Error closing {exchange_id} exchange: {e}")
        
        self.exchanges.clear()
        self.tasks.clear()
        logger.info("All WebSocket connections stopped")
    
    async def health_check(self) -> Dict[str, Any]:
        try:
            exchange_status = {}
            
            for exchange_id, exchange in self.exchanges.items():
                try:
                    markets = len(exchange.markets) if exchange.markets else 0
                    exchange_status[exchange_id] = {
                        "status": "connected",
                        "markets_loaded": markets,
                        "symbols_watching": len([s for s in self.symbols if s in exchange.markets])
                    }
                except Exception as e:
                    exchange_status[exchange_id] = {
                        "status": "error",
                        "error": str(e)
                    }
            
            active_tasks = len([task for task in self.tasks if not task.done()])
            
            return {
                "status": "healthy" if self.running else "stopped",
                "exchanges": exchange_status,
                "active_websocket_tasks": active_tasks,
                "total_symbols": len(self.symbols),
                "running": self.running
            }
            
        except Exception as e:
            logger.error(f"WebSocket health check failed: {e}")
            return {"status": "error", "message": str(e)}
