"""
WebSocket Manager for Real-Time Data Collection
Prioritizes WebSocket connections for maximum performance
"""

import asyncio
import websockets
import json
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import threading
import time

logger = logging.getLogger(__name__)

class WebSocketManager:
    """Manages WebSocket connections for real-time trading data"""
    
    def __init__(self):
        self.connections = {}
        self.callbacks = {}
        self.running = False
        self.reconnect_attempts = {}
        self.max_reconnect_attempts = 5
        
    async def connect_binance_stream(self, symbols: list, callback: Callable):
        """Connect to Binance WebSocket stream for real-time data"""
        streams = []
        for symbol in symbols:
            symbol_lower = symbol.lower()
            streams.extend([
                f"{symbol_lower}@ticker",
                f"{symbol_lower}@depth5",
                f"{symbol_lower}@kline_1m"
            ])
        
        stream_names = "/".join(streams)
        uri = f"wss://stream.binance.com:9443/ws/{stream_names}"
        
        logger.info(f"🚀 Connecting to Binance WebSocket: {len(symbols)} symbols")
        
        try:
            async with websockets.connect(uri) as websocket:
                self.connections['binance'] = websocket
                self.callbacks['binance'] = callback
                
                logger.info("✅ Binance WebSocket connected successfully")
                
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        processed_data = self._process_binance_data(data)
                        if processed_data and callback:
                            await callback('binance', processed_data)
                    except Exception as e:
                        logger.error(f"❌ Error processing Binance data: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Binance WebSocket connection failed: {e}")
            await self._handle_reconnect('binance', uri, callback)
    
    async def connect_kraken_stream(self, symbols: list, callback: Callable):
        """Connect to Kraken WebSocket stream"""
        uri = "wss://ws.kraken.com/"
        
        logger.info(f"🚀 Connecting to Kraken WebSocket: {len(symbols)} symbols")
        
        try:
            async with websockets.connect(uri) as websocket:
                self.connections['kraken'] = websocket
                self.callbacks['kraken'] = callback
                
                subscribe_msg = {
                    "event": "subscribe",
                    "pair": symbols,
                    "subscription": {"name": "ticker"}
                }
                
                await websocket.send(json.dumps(subscribe_msg))
                logger.info("✅ Kraken WebSocket connected and subscribed")
                
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        processed_data = self._process_kraken_data(data)
                        if processed_data and callback:
                            await callback('kraken', processed_data)
                    except Exception as e:
                        logger.error(f"❌ Error processing Kraken data: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Kraken WebSocket connection failed: {e}")
            await self._handle_reconnect('kraken', uri, callback)
    
    def _process_binance_data(self, data: Dict) -> Optional[Dict]:
        """Process Binance WebSocket data"""
        try:
            if 'stream' in data and 'data' in data:
                stream_data = data['data']
                stream_name = data['stream']
                
                if '@ticker' in stream_name:
                    return {
                        'type': 'ticker',
                        'symbol': stream_data.get('s'),
                        'price': float(stream_data.get('c', 0)),
                        'volume': float(stream_data.get('v', 0)),
                        'change_24h': float(stream_data.get('P', 0)),
                        'high_24h': float(stream_data.get('h', 0)),
                        'low_24h': float(stream_data.get('l', 0)),
                        'timestamp': stream_data.get('E', int(time.time() * 1000)),
                        'source': 'binance_ws'
                    }
                elif '@depth' in stream_name:
                    return {
                        'type': 'orderbook',
                        'symbol': stream_data.get('s'),
                        'bids': [[float(bid[0]), float(bid[1])] for bid in stream_data.get('bids', [])],
                        'asks': [[float(ask[0]), float(ask[1])] for ask in stream_data.get('asks', [])],
                        'timestamp': int(time.time() * 1000),
                        'source': 'binance_ws'
                    }
                elif '@kline' in stream_name:
                    kline = stream_data.get('k', {})
                    return {
                        'type': 'kline',
                        'symbol': kline.get('s'),
                        'open': float(kline.get('o', 0)),
                        'high': float(kline.get('h', 0)),
                        'low': float(kline.get('l', 0)),
                        'close': float(kline.get('c', 0)),
                        'volume': float(kline.get('v', 0)),
                        'timestamp': kline.get('t', int(time.time() * 1000)),
                        'source': 'binance_ws'
                    }
        except Exception as e:
            logger.error(f"❌ Error processing Binance data: {e}")
        
        return None
    
    def _process_kraken_data(self, data: Dict) -> Optional[Dict]:
        """Process Kraken WebSocket data"""
        try:
            if isinstance(data, list) and len(data) >= 4:
                if data[2] == "ticker":
                    ticker_data = data[1]
                    symbol = data[3]
                    
                    return {
                        'type': 'ticker',
                        'symbol': symbol,
                        'price': float(ticker_data.get('c', [0, 0])[0]),
                        'volume': float(ticker_data.get('v', [0, 0])[1]),
                        'high_24h': float(ticker_data.get('h', [0, 0])[1]),
                        'low_24h': float(ticker_data.get('l', [0, 0])[1]),
                        'timestamp': int(time.time() * 1000),
                        'source': 'kraken_ws'
                    }
        except Exception as e:
            logger.error(f"❌ Error processing Kraken data: {e}")
        
        return None
    
    async def _handle_reconnect(self, exchange: str, uri: str, callback: Callable):
        """Handle WebSocket reconnection logic"""
        if exchange not in self.reconnect_attempts:
            self.reconnect_attempts[exchange] = 0
        
        if self.reconnect_attempts[exchange] < self.max_reconnect_attempts:
            self.reconnect_attempts[exchange] += 1
            wait_time = min(2 ** self.reconnect_attempts[exchange], 60)
            
            logger.warning(f"🔄 Reconnecting to {exchange} in {wait_time}s (attempt {self.reconnect_attempts[exchange]})")
            await asyncio.sleep(wait_time)
            
            if exchange == 'binance':
                await self.connect_binance_stream(['BTCUSDT', 'ETHUSDT'], callback)
            elif exchange == 'kraken':
                await self.connect_kraken_stream(['XBT/USD', 'ETH/USD'], callback)
        else:
            logger.error(f"❌ Max reconnection attempts reached for {exchange}")
    
    async def start_all_streams(self, callback: Callable):
        """Start all WebSocket streams simultaneously"""
        logger.info("🚀 Starting all WebSocket streams...")
        
        tasks = [
            self.connect_binance_stream(['BTCUSDT', 'ETHUSDT'], callback),
            self.connect_kraken_stream(['XBT/USD', 'ETH/USD'], callback)
        ]
        
        self.running = True
        await asyncio.gather(*tasks, return_exceptions=True)
    
    def stop_all_streams(self):
        """Stop all WebSocket streams"""
        logger.info("🛑 Stopping all WebSocket streams...")
        self.running = False
        
        for exchange, connection in self.connections.items():
            try:
                if hasattr(connection, 'close'):
                    asyncio.create_task(connection.close())
                logger.info(f"✅ Stopped {exchange} WebSocket")
            except Exception as e:
                logger.error(f"❌ Error stopping {exchange} WebSocket: {e}")
        
        self.connections.clear()
        self.callbacks.clear()
        self.reconnect_attempts.clear()
