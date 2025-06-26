import asyncio
import pandas as pd
import numpy as np
from typing import Dict, Any, Callable, List
from datetime import datetime, timedelta
import sys
import os

# Add the project root to the path
sys.path.append('/root/Projet_AUTOBOT/src')

from autobot.config import load_api_keys
from autobot.providers import binance, alphavantage, twelvedata

class LiveDataPipeline:
    """Pipeline for streaming live market data to trading strategies"""
    
    def __init__(self):
        self.subscribers = []
        self.running = False
        self.data_cache = {}
        
        # Load API keys on initialization
        load_api_keys()
    
    def subscribe(self, callback: Callable[[pd.DataFrame], None]):
        """Subscribe to live data updates"""
        self.subscribers.append(callback)
    
    def get_historical_data(self, symbol: str = "BTCUSDT", periods: int = 100) -> pd.DataFrame:
        """Get historical market data for backtesting"""
        try:
            # Get klines data from Binance
            klines = binance.get_klines(symbol, "1h", periods)
            
            if 'error' in klines:
                print(f"Error fetching data: {klines['error']}")
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            # Convert to proper types
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            df.set_index('timestamp', inplace=True)
            return df[['open', 'high', 'low', 'close', 'volume']]
            
        except Exception as e:
            print(f"Error in get_historical_data: {e}")
            return pd.DataFrame()
    
    def get_live_ticker(self, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """Get live ticker data"""
        try:
            ticker = binance.get_ticker(symbol)
            if 'error' not in ticker:
                return {
                    'symbol': ticker.get('symbol'),
                    'price': float(ticker.get('lastPrice', 0)),
                    'change_24h': float(ticker.get('priceChangePercent', 0)),
                    'volume_24h': float(ticker.get('volume', 0)),
                    'timestamp': datetime.now()
                }
        except Exception as e:
            print(f"Error getting live ticker: {e}")
        
        return {}
    
    async def start_streaming(self, symbols: List[str] = ["BTCUSDT", "ETHUSDT"], interval: int = 60):
        """Start streaming live market data"""
        self.running = True
        
        while self.running:
            try:
                combined_data = []
                
                # Get data for each symbol
                for symbol in symbols:
                    ticker = self.get_live_ticker(symbol)
                    if ticker:
                        combined_data.append(ticker)
                
                if combined_data:
                    # Convert to DataFrame
                    df = pd.DataFrame(combined_data)
                    
                    # Notify all subscribers
                    for callback in self.subscribers:
                        try:
                            callback(df)
                        except Exception as e:
                            print(f"Error in subscriber callback: {e}")
                
                await asyncio.sleep(interval)
                
            except Exception as e:
                print(f"Error in data pipeline: {e}")
                await asyncio.sleep(interval)
    
    def stop_streaming(self):
        """Stop the data streaming"""
        self.running = False

# Global instance
live_pipeline = LiveDataPipeline()
