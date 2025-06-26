"""
Multi-API Data Fusion System for AUTOBOT
Collects data from ALL APIs simultaneously for maximum precision
Enhanced with WebSocket prioritization for ultra-low latency
"""

import os
import sys
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import json
import logging
import time
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps

sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

from autobot.data.websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)

class MultiAPIDataFusion:
    """Advanced multi-API data fusion system for maximum precision with WebSocket prioritization"""
    
    def __init__(self):
        self.api_keys = self._load_api_keys()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'AUTOBOT-Trading-System/1.0'
        })
        self.websocket_manager = WebSocketManager()
        self.websocket_data = {}
        self.websocket_active = False
        
        self.api_status = {
            'binance_ws': {'active': False, 'calls_today': 0, 'last_success': None, 'data_quality': 0.0, 'latency_ms': 0},
            'kraken_ws': {'active': False, 'calls_today': 0, 'last_success': None, 'data_quality': 0.0, 'latency_ms': 0},
            'binance': {'active': True, 'calls_today': 0, 'last_success': None, 'data_quality': 0.0, 'latency_ms': 200},
            'twelvedata': {'active': True, 'calls_today': 0, 'last_success': None, 'data_quality': 0.0, 'latency_ms': 400},
            'alphavantage': {'active': True, 'calls_today': 0, 'last_success': None, 'data_quality': 0.0, 'latency_ms': 600},
            'fred': {'active': True, 'calls_today': 0, 'last_success': None, 'data_quality': 0.0, 'latency_ms': 800},
            'newsapi': {'active': True, 'calls_today': 0, 'last_success': None, 'data_quality': 0.0, 'latency_ms': 500},
            'coinbase': {'active': True, 'calls_today': 0, 'last_success': None, 'data_quality': 0.0, 'latency_ms': 300},
            'kraken': {'active': True, 'calls_today': 0, 'last_success': None, 'data_quality': 0.0, 'latency_ms': 350}
        }
        self.data_cache = {}
        self.fusion_results = {}
        self.performance_metrics = {
            'total_calls': 0,
            'websocket_calls': 0,
            'rest_calls': 0,
            'average_latency': 0,
            'data_quality_avg': 0.0
        }
        
    def _load_api_keys(self):
        """Load API keys from configuration file"""
        try:
            config_path = "/home/ubuntu/repos/Projet_AUTOBOT/config/api_keys.json"
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    return json.load(f)
            else:
                logger.warning(f"API keys file not found at {config_path}")
                return {}
        except Exception as e:
            logger.error(f"Error loading API keys: {e}")
            return {}
    
    async def start_websocket_streams(self):
        """Start WebSocket streams for real-time data"""
        if not self.websocket_active:
            logger.info("🚀 Starting WebSocket streams for ultra-low latency data...")
            
            async def websocket_callback(exchange: str, data: Dict):
                """Handle incoming WebSocket data"""
                self.websocket_data[exchange] = data
                self.api_status[f"{exchange}_ws"]['active'] = True
                self.api_status[f"{exchange}_ws"]['last_success'] = time.time()
                self.api_status[f"{exchange}_ws"]['data_quality'] = self._calculate_data_quality(data)
                self.performance_metrics['websocket_calls'] += 1
                
                logger.debug(f"📡 {exchange.upper()} WebSocket: {data.get('type', 'unknown')} data received")
            
            try:
                asyncio.create_task(self.websocket_manager.start_all_streams(websocket_callback))
                self.websocket_active = True
                logger.info("✅ WebSocket streams started successfully")
            except Exception as e:
                logger.error(f"❌ Failed to start WebSocket streams: {e}")
    
    def collect_all_data_simultaneously(self, symbol: str, asset_type: str = "crypto") -> Dict[str, Any]:
        """Collect data from ALL APIs simultaneously with WebSocket prioritization"""
        start_time = time.time()
        logger.info(f"🎯 Starting ENHANCED multi-API fusion for {symbol} (WebSocket + REST)")
        
        results = {
            'symbol': symbol,
            'asset_type': asset_type,
            'timestamp': start_time,
            'sources': [],
            'prices': [],
            'volumes': [],
            'technical_indicators': {},
            'sentiment_data': {},
            'economic_data': {},
            'news_data': {},
            'exchange_data': {},
            'websocket_data': {},
            'combined_signal': 0.0,
            'data_quality_score': 0.0,
            'api_contributions': {},
            'performance_metrics': {
                'collection_time_ms': 0,
                'websocket_sources': 0,
                'rest_sources': 0,
                'total_latency_ms': 0
            }
        }
        
        if self.websocket_active and self.websocket_data:
            for exchange, ws_data in self.websocket_data.items():
                if ws_data and time.time() - ws_data.get('timestamp', 0) / 1000 < 5:  # Data less than 5 seconds old
                    results['sources'].append(f"{exchange}_ws")
                    results['websocket_data'][exchange] = ws_data
                    results['api_contributions'][f"{exchange}_ws"] = ws_data
                    results['performance_metrics']['websocket_sources'] += 1
                    
                    if 'price' in ws_data:
                        results['prices'].append(ws_data['price'])
                    if 'volume' in ws_data:
                        results['volumes'].append(ws_data['volume'])
                    
                    logger.info(f"⚡ {exchange.upper()} WebSocket: Real-time data used (latency ~10-50ms)")
        
        
        with ThreadPoolExecutor(max_workers=7) as executor:
            rest_apis = {}
            
            if not (self.websocket_active and 'binance' in self.websocket_data):
                rest_apis[executor.submit(self._get_binance_data, symbol)] = 'binance'
            
            if not (self.websocket_active and 'kraken' in self.websocket_data):
                rest_apis[executor.submit(self._get_kraken_data, symbol)] = 'kraken'
            
            rest_apis.update({
                executor.submit(self._get_coinbase_data, symbol): 'coinbase',
                executor.submit(self._get_twelvedata_data, symbol): 'twelvedata',
                executor.submit(self._get_alphavantage_data, symbol, asset_type): 'alphavantage',
                executor.submit(self._get_fred_data): 'fred',
                executor.submit(self._get_news_data, symbol): 'newsapi'
            })
            
            for future in as_completed(rest_apis):
                api_name = rest_apis[future]
                api_start_time = time.time()
                
                try:
                    api_data = future.result(timeout=10)  # 10 second timeout per API
                    api_latency = (time.time() - api_start_time) * 1000  # Convert to ms
                    
                    if api_data:
                        results['sources'].append(api_name)
                        results['api_contributions'][api_name] = api_data
                        results['performance_metrics']['rest_sources'] += 1
                        results['performance_metrics']['total_latency_ms'] += api_latency
                        
                        if 'price' in api_data:
                            results['prices'].append(api_data['price'])
                        if 'volume' in api_data:
                            results['volumes'].append(api_data['volume'])
                            
                        for key, value in api_data.items():
                            if key.endswith('_indicator') or key in ['rsi', 'macd', 'sma', 'ema']:
                                results['technical_indicators'][f"{api_name}_{key}"] = value
                        
                        if api_name == 'newsapi' and 'sentiment' in api_data:
                            results['sentiment_data'] = api_data['sentiment']
                            results['news_data'] = api_data.get('articles', [])
                            
                        if api_name == 'fred' and 'indicators' in api_data:
                            results['economic_data'] = api_data['indicators']
                            
                        self.api_status[api_name]['last_success'] = time.time()
                        self.api_status[api_name]['calls_today'] += 1
                        self.api_status[api_name]['data_quality'] = self._calculate_data_quality(api_data)
                        self.api_status[api_name]['latency_ms'] = api_latency
                        self.performance_metrics['rest_calls'] += 1
                        
                        logger.info(f"✅ {api_name.upper()} REST API: Data collected ({api_latency:.0f}ms)")
                    else:
                        logger.warning(f"❌ {api_name.upper()} API: No data returned")
                        self.api_status[api_name]['active'] = False
                        
                except Exception as e:
                    logger.error(f"❌ {api_name.upper()} API error: {e}")
                    self.api_status[api_name]['active'] = False
        
        # Calculate performance metrics
        total_time = (time.time() - start_time) * 1000
        results['performance_metrics']['collection_time_ms'] = total_time
        
        if results['performance_metrics']['rest_sources'] > 0:
            results['performance_metrics']['average_rest_latency_ms'] = (
                results['performance_metrics']['total_latency_ms'] / results['performance_metrics']['rest_sources']
            )
        
        results['combined_signal'] = self._calculate_fusion_signal(results)
        results['data_quality_score'] = self._calculate_overall_quality(results)
        
        self.fusion_results[symbol] = results
        self.performance_metrics['total_calls'] += 1
        
        if results['data_quality_score'] > 0:
            self.performance_metrics['data_quality_avg'] = (
                (self.performance_metrics['data_quality_avg'] * (self.performance_metrics['total_calls'] - 1) + 
                 results['data_quality_score']) / self.performance_metrics['total_calls']
            )
        
        total_sources = len(results['sources'])
        ws_sources = results['performance_metrics']['websocket_sources']
        rest_sources = results['performance_metrics']['rest_sources']
        
        logger.info(f"🎯 ENHANCED Multi-API fusion complete for {symbol}:")
        logger.info(f"   📡 WebSocket sources: {ws_sources} (ultra-low latency)")
        logger.info(f"   🌐 REST sources: {rest_sources} (avg {results['performance_metrics'].get('average_rest_latency_ms', 0):.0f}ms)")
        logger.info(f"   📊 Total sources: {total_sources}/9 APIs active")
        logger.info(f"   ⚡ Collection time: {total_time:.0f}ms")
        logger.info(f"   📈 Data quality: {results['data_quality_score']:.2f}")
        logger.info(f"   🎯 Combined signal: {results['combined_signal']:.4f}")
        
        return results
    
    def _get_binance_data(self, symbol: str) -> Dict[str, Any]:
        """Get data from Binance API"""
        try:
            url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
            response = self.session.get(url, timeout=8)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'price': float(data.get('lastPrice', 0)),
                    'volume': float(data.get('volume', 0)),
                    'change_24h': float(data.get('priceChangePercent', 0)),
                    'high_24h': float(data.get('highPrice', 0)),
                    'low_24h': float(data.get('lowPrice', 0)),
                    'rsi_indicator': 50 + float(data.get('priceChangePercent', 0)) * 0.5,
                    'source': 'binance'
                }
        except Exception as e:
            logger.debug(f"Binance API error: {e}")
        return None
    
    def _get_coinbase_data(self, symbol: str) -> Dict[str, Any]:
        """Get data from Coinbase API"""
        try:
            if symbol.endswith('USDT'):
                cb_symbol = symbol.replace('USDT', '-USD')
            else:
                cb_symbol = symbol
                
            url = f"https://api.coinbase.com/v2/exchange-rates?currency={cb_symbol.split('-')[0]}"
            response = self.session.get(url, timeout=8)
            
            if response.status_code == 200:
                data = response.json()
                usd_rate = data.get('data', {}).get('rates', {}).get('USD', 0)
                if usd_rate:
                    return {
                        'price': float(usd_rate),
                        'volume': 500000,  # Estimate
                        'source': 'coinbase'
                    }
        except Exception as e:
            logger.debug(f"Coinbase API error: {e}")
        return None
    
    def _get_kraken_data(self, symbol: str) -> Dict[str, Any]:
        """Get data from Kraken API"""
        try:
            if symbol == 'BTCUSDT':
                kraken_symbol = 'XBTUSD'
            elif symbol == 'ETHUSDT':
                kraken_symbol = 'ETHUSD'
            else:
                kraken_symbol = symbol
                
            url = f"https://api.kraken.com/0/public/Ticker?pair={kraken_symbol}"
            response = self.session.get(url, timeout=8)
            
            if response.status_code == 200:
                data = response.json()
                if 'result' in data and data['result']:
                    pair_data = list(data['result'].values())[0]
                    return {
                        'price': float(pair_data.get('c', [0])[0]),  # Last trade price
                        'volume': float(pair_data.get('v', [0])[1]),  # 24h volume
                        'high_24h': float(pair_data.get('h', [0])[1]),
                        'low_24h': float(pair_data.get('l', [0])[1]),
                        'source': 'kraken'
                    }
        except Exception as e:
            logger.debug(f"Kraken API error: {e}")
        return None
    
    def _get_twelvedata_data(self, symbol: str) -> Dict[str, Any]:
        """Get data from TwelveData API (with quota management)"""
        try:
            api_key = self.api_keys.get('TWELVE_DATA_API_KEY')
            if not api_key or self.api_status['twelvedata']['calls_today'] > 750:
                return None
                
            url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={api_key}"
            response = self.session.get(url, timeout=8)
            
            if response.status_code == 200:
                data = response.json()
                if 'price' in data:
                    return {
                        'price': float(data['price']),
                        'source': 'twelvedata'
                    }
        except Exception as e:
            logger.debug(f"TwelveData API error: {e}")
        return None
    
    def _get_alphavantage_data(self, symbol: str, asset_type: str) -> Dict[str, Any]:
        """Get data from AlphaVantage API"""
        try:
            api_key = self.api_keys.get('ALPHA_VANTAGE_API_KEY')
            if not api_key:
                return None
                
            if asset_type == "crypto":
                url = f"https://www.alphavantage.co/query?function=DIGITAL_CURRENCY_DAILY&symbol={symbol.replace('USDT', '')}&market=USD&apikey={api_key}"
            elif asset_type == "forex":
                url = f"https://www.alphavantage.co/query?function=FX_DAILY&from_symbol={symbol.split('/')[0]}&to_symbol={symbol.split('/')[1]}&apikey={api_key}"
            else:
                url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}"
                
            response = self.session.get(url, timeout=8)
            
            if response.status_code == 200:
                data = response.json()
                
                price = 0
                if 'Realtime Currency Exchange Rate' in data:
                    price = float(data['Realtime Currency Exchange Rate']['5. Exchange Rate'])
                elif 'Global Quote' in data:
                    price = float(data['Global Quote']['05. price'])
                elif 'Time Series (Digital Currency Daily)' in data:
                    latest_date = list(data['Time Series (Digital Currency Daily)'].keys())[0]
                    price = float(data['Time Series (Digital Currency Daily)'][latest_date]['4a. close (USD)'])
                
                if price > 0:
                    return {
                        'price': price,
                        'sma_indicator': price * 0.98,  # Estimate SMA
                        'source': 'alphavantage'
                    }
        except Exception as e:
            logger.debug(f"AlphaVantage API error: {e}")
        return None
    
    def _get_fred_data(self) -> Dict[str, Any]:
        """Get economic indicators from FRED"""
        try:
            api_key = self.api_keys.get('FRED_API_KEY')
            if not api_key:
                return None
                
            indicators = {
                'DGS10': 'treasury_10y',  # 10-Year Treasury Rate
                'DEXUSEU': 'usd_eur_rate',  # USD/EUR Exchange Rate
                'DCOILWTICO': 'oil_price'  # Oil Price
            }
            
            results = {}
            for fred_id, name in indicators.items():
                try:
                    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={fred_id}&api_key={api_key}&file_type=json&limit=1&sort_order=desc"
                    response = self.session.get(url, timeout=5)
                    
                    if response.status_code == 200:
                        data = response.json()
                        observations = data.get('observations', [])
                        if observations and observations[0].get('value') != '.':
                            results[name] = float(observations[0]['value'])
                except Exception as e:
                    logger.debug(f"FRED indicator {fred_id} error: {e}")
                    
            if results:
                return {
                    'indicators': results,
                    'source': 'fred'
                }
        except Exception as e:
            logger.debug(f"FRED API error: {e}")
        return None
    
    def _get_news_data(self, symbol: str) -> Dict[str, Any]:
        """Get news sentiment from NewsAPI"""
        try:
            api_key = self.api_keys.get('NEWSAPI_API_KEY')
            if not api_key:
                return None
                
            query = symbol.replace('USDT', '').replace('USD', '')  # BTC, ETH, etc.
            url = f"https://newsapi.org/v2/everything?q={query}&sortBy=publishedAt&pageSize=5&apiKey={api_key}"
            
            response = self.session.get(url, timeout=8)
            if response.status_code == 200:
                data = response.json()
                articles = data.get('articles', [])
                sentiment_score = self._analyze_sentiment(articles)
                
                return {
                    'sentiment': {
                        'score': sentiment_score,
                        'article_count': len(articles),
                        'latest_headline': articles[0].get('title', '') if articles else ''
                    },
                    'articles': articles[:3],  # Top 3 articles
                    'source': 'newsapi'
                }
        except Exception as e:
            logger.debug(f"NewsAPI error: {e}")
        return None
    
    def _analyze_sentiment(self, articles: List[Dict]) -> float:
        """Simple sentiment analysis of news articles"""
        if not articles:
            return 0.0
            
        positive_words = ['bull', 'rise', 'gain', 'up', 'high', 'surge', 'rally', 'positive', 'growth', 'buy']
        negative_words = ['bear', 'fall', 'drop', 'down', 'low', 'crash', 'decline', 'negative', 'loss', 'sell']
        
        total_score = 0
        for article in articles[:5]:  # Analyze first 5 articles
            title = article.get('title', '').lower()
            description = article.get('description', '').lower()
            text = f"{title} {description}"
            
            pos_count = sum(1 for word in positive_words if word in text)
            neg_count = sum(1 for word in negative_words if word in text)
            
            total_score += (pos_count - neg_count)
            
        return max(-1.0, min(1.0, total_score / 10))  # Normalize to [-1, 1]
    
    def _calculate_data_quality(self, api_data: Dict[str, Any]) -> float:
        """Calculate data quality score for an API response"""
        if not api_data:
            return 0.0
            
        quality = 0.0
        
        if 'price' in api_data and api_data['price'] > 0:
            quality += 0.4
            
        if 'volume' in api_data and api_data['volume'] > 0:
            quality += 0.2
            
        indicators = ['rsi_indicator', 'macd', 'sma', 'ema']
        for indicator in indicators:
            if indicator in api_data:
                quality += 0.1
                
        if 'high_24h' in api_data or 'low_24h' in api_data:
            quality += 0.1
            
        return min(1.0, quality)
    
    def _calculate_fusion_signal(self, results: Dict[str, Any]) -> float:
        """Calculate combined trading signal from all data sources"""
        signal = 0.0
        weight_sum = 0.0
        
        if results['prices'] and len(results['prices']) > 1:
            avg_price = sum(results['prices']) / len(results['prices'])
            price_variance = sum((p - avg_price) ** 2 for p in results['prices']) / len(results['prices'])
            price_consensus = 1.0 - min(1.0, price_variance / (avg_price * 0.01))  # Lower variance = better consensus
            signal += price_consensus * 0.4
            weight_sum += 0.4
            
        if results['technical_indicators']:
            tech_signal = 0.0
            indicator_count = 0
            
            for key, value in results['technical_indicators'].items():
                if 'rsi' in key.lower():
                    if value < 30:
                        tech_signal += 0.3  # Oversold - buy signal
                    elif value > 70:
                        tech_signal -= 0.3  # Overbought - sell signal
                    indicator_count += 1
                elif 'macd' in key.lower():
                    tech_signal += max(-0.2, min(0.2, value * 0.01))
                    indicator_count += 1
                    
            if indicator_count > 0:
                signal += (tech_signal / indicator_count) * 0.3
                weight_sum += 0.3
                
        if results['sentiment_data']:
            sentiment_score = results['sentiment_data'].get('score', 0)
            signal += sentiment_score * 0.2
            weight_sum += 0.2
            
        if results['economic_data']:
            econ_signal = 0.0
            if 'treasury_10y' in results['economic_data']:
                treasury = results['economic_data']['treasury_10y']
                econ_signal += max(-0.1, min(0.1, (treasury - 4.0) * 0.02))  # Relative to 4% baseline
                
            signal += econ_signal * 0.1
            weight_sum += 0.1
            
        return signal / weight_sum if weight_sum > 0 else 0.0
    
    def _calculate_overall_quality(self, results: Dict[str, Any]) -> float:
        """Calculate overall data quality score"""
        if not results['sources']:
            return 0.0
            
        source_quality = len(results['sources']) / 7.0  # 7 total APIs
        
        api_quality = 0.0
        for api_name in results['sources']:
            api_quality += self.api_status[api_name]['data_quality']
            
        avg_api_quality = api_quality / len(results['sources']) if results['sources'] else 0.0
        
        overall_quality = (source_quality * 0.6) + (avg_api_quality * 0.4)
        
        return min(1.0, overall_quality)
    
    def get_fusion_summary(self) -> Dict[str, Any]:
        """Get comprehensive summary of enhanced fusion system performance"""
        active_apis = sum(1 for status in self.api_status.values() if status['active'])
        total_calls = sum(status['calls_today'] for status in self.api_status.values())
        avg_quality = sum(status['data_quality'] for status in self.api_status.values()) / len(self.api_status)
        
        # WebSocket performance metrics
        ws_active = sum(1 for api, status in self.api_status.items() if api.endswith('_ws') and status['active'])
        avg_latency = np.mean([status['latency_ms'] for status in self.api_status.values() if status['latency_ms'] > 0])
        
        return {
            'active_apis': active_apis,
            'total_apis': len(self.api_status),
            'websocket_active': self.websocket_active,
            'websocket_sources_active': ws_active,
            'total_calls_today': total_calls,
            'average_data_quality': float(avg_quality) if not np.isnan(avg_quality) else 0.0,
            'average_latency_ms': float(avg_latency) if not np.isnan(avg_latency) else 0.0,
            'performance_metrics': self.performance_metrics,
            'api_status': self.api_status,
            'fusion_results_count': len(self.fusion_results),
            'last_fusion_time': max([r['timestamp'] for r in self.fusion_results.values()]) if self.fusion_results else 0,
            'optimization_recommendations': self._get_optimization_recommendations()
        }
    
    def _get_optimization_recommendations(self) -> List[str]:
        """Get performance optimization recommendations"""
        recommendations = []
        
        if not self.websocket_active:
            recommendations.append("🚀 Enable WebSocket streams for ultra-low latency (10-50ms vs 200-800ms REST)")
        
        if self.api_status['twelvedata']['calls_today'] > 700:
            recommendations.append("⚠️ TwelveData approaching daily limit - upgrade to Pro plan ($29/month) recommended")
        
        if self.performance_metrics['data_quality_avg'] < 0.7:
            recommendations.append("📊 Data quality below optimal - check API key validity and network connectivity")
        
        high_latency_apis = [api for api, status in self.api_status.items() 
                           if status['latency_ms'] > 1000 and status['active']]
        if high_latency_apis:
            recommendations.append(f"⚡ High latency detected on: {', '.join(high_latency_apis)} - consider regional API endpoints")
        
        if self.performance_metrics['websocket_calls'] < self.performance_metrics['rest_calls'] * 0.1:
            recommendations.append("📡 WebSocket usage low - increase real-time data prioritization for better performance")
        
        return recommendations
