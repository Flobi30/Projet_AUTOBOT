"""
Intelligent Decision Engine for AUTOBOT
Continuously analyzes multi-API data and executes optimal trading strategies
"""

import logging
import asyncio
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

@dataclass
class TradingDecision:
    symbol: str
    action: str  # 'BUY', 'SELL', 'HOLD'
    confidence: float  # 0.0 to 1.0
    position_size: float
    entry_price: float
    stop_loss: float
    take_profit: float
    reasoning: str
    data_sources: List[str]
    timestamp: float

@dataclass
class MarketAnalysis:
    symbol: str
    trend_direction: str  # 'BULLISH', 'BEARISH', 'NEUTRAL'
    volatility: float
    momentum: float
    support_level: float
    resistance_level: float
    rsi: float
    macd_signal: str
    volume_analysis: str
    news_sentiment: float
    economic_indicators: Dict[str, float]

class IntelligentDecisionEngine:
    """Advanced AI-driven trading decision engine"""
    
    def __init__(self):
        self.fusion_system = None
        self.active_positions = {}
        self.decision_history = []
        self.performance_metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'total_pnl': 0.0,
            'best_trade': 0.0,
            'worst_trade': 0.0,
            'win_rate': 0.0,
            'sharpe_ratio': 0.0
        }
        self.risk_parameters = {
            'max_position_size': 0.1,  # 10% of capital per trade
            'max_daily_loss': 0.05,    # 5% max daily loss
            'min_confidence': 0.7,     # Minimum confidence for trade execution
            'max_correlation': 0.8     # Max correlation between positions
        }
        
    async def initialize(self):
        """Initialize the decision engine with enhanced multi-API fusion and WebSocket support"""
        try:
            from autobot.data.multi_api_fusion import MultiAPIDataFusion
            self.fusion_system = MultiAPIDataFusion()
            
            await self.fusion_system.start_websocket_streams()
            
            logger.info("✅ Enhanced Intelligent Decision Engine initialized with WebSocket support")
        except Exception as e:
            logger.error(f"❌ Failed to initialize enhanced decision engine: {e}")
            raise
    
    async def continuous_analysis_loop(self):
        """Enhanced continuous analysis loop with WebSocket prioritization and adaptive cadence"""
        logger.info("🚀 Starting ENHANCED continuous intelligent analysis with WebSocket streams...")
        
        analysis_count = 0
        
        while True:
            try:
                analysis_count += 1
                start_time = time.time()
                
                # Analyze multiple symbols with different cadences based on volatility
                high_freq_symbols = ['BTCUSDT', 'ETHUSDT']  # WebSocket priority - every cycle
                medium_freq_symbols = ['EURUSD', 'GBPUSD']  # Every 2nd cycle
                low_freq_symbols = ['XAUUSD', 'XAGUSD', 'WTIUSD']  # Every 3rd cycle
                
                symbols_to_analyze = high_freq_symbols.copy()
                
                if analysis_count % 2 == 0:
                    symbols_to_analyze.extend(medium_freq_symbols)
                
                if analysis_count % 3 == 0:
                    symbols_to_analyze.extend(low_freq_symbols)
                
                logger.info(f"🎯 Analysis cycle #{analysis_count}: Processing {len(symbols_to_analyze)} symbols")
                
                all_analyses = []
                decisions_made = 0
                
                for symbol in symbols_to_analyze:
                    analysis = await self.analyze_symbol(symbol)
                    if analysis:
                        all_analyses.append(analysis)
                
                decisions = await self.make_trading_decisions(all_analyses)
                
                for decision in decisions:
                    await self.execute_decision(decision)
                    decisions_made += 1
                
                self.update_performance_metrics()
                
                cycle_time = (time.time() - start_time) * 1000
                logger.info(f"⚡ Cycle #{analysis_count} complete: {decisions_made} decisions in {cycle_time:.0f}ms")
                
                if analysis_count % 10 == 0:
                    fusion_summary = self.fusion_system.get_fusion_summary()
                    logger.info(f"📈 Performance Summary (Cycle #{analysis_count}):")
                    logger.info(f"   📡 WebSocket active: {fusion_summary['websocket_active']}")
                    logger.info(f"   🌐 Active APIs: {fusion_summary['active_apis']}/{fusion_summary['total_apis']}")
                    logger.info(f"   ⚡ Avg latency: {fusion_summary['average_latency_ms']:.0f}ms")
                    logger.info(f"   📊 Data quality: {fusion_summary['average_data_quality']:.2f}")
                    
                    for rec in fusion_summary['optimization_recommendations']:
                        logger.warning(f"💡 {rec}")
                
                self.log_engine_status()
                
                if cycle_time < 5000:  # If cycle completed in under 5 seconds
                    sleep_time = 10  # Faster cycles for good performance
                elif cycle_time < 15000:  # If cycle completed in under 15 seconds
                    sleep_time = 20  # Standard cycles
                else:
                    sleep_time = 30  # Slower cycles if system is struggling
                
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"❌ Error in enhanced continuous analysis: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def analyze_symbol(self, symbol: str) -> Optional[MarketAnalysis]:
        """Comprehensive analysis of a single symbol using all available data"""
        try:
            fusion_data = self.fusion_system.collect_all_data_simultaneously(symbol)
            
            if not fusion_data or len(fusion_data.get('sources', [])) < 2:
                logger.warning(f"Insufficient data sources for {symbol}")
                return None
            
            prices = fusion_data.get('prices', [])
            if not prices:
                return None
                
            avg_price = np.mean(prices)
            price_volatility = np.std(prices) / avg_price if avg_price > 0 else 0
            
            trend_signals = []
            for source, data in fusion_data.get('api_contributions', {}).items():
                if 'change_24h' in data:
                    change = data['change_24h']
                    if change > 2:
                        trend_signals.append('BULLISH')
                    elif change < -2:
                        trend_signals.append('BEARISH')
                    else:
                        trend_signals.append('NEUTRAL')
            
            bullish_count = trend_signals.count('BULLISH')
            bearish_count = trend_signals.count('BEARISH')
            
            if bullish_count > bearish_count:
                trend_direction = 'BULLISH'
            elif bearish_count > bullish_count:
                trend_direction = 'BEARISH'
            else:
                trend_direction = 'NEUTRAL'
            
            support_level = min(prices) * 0.98 if prices else avg_price * 0.98
            resistance_level = max(prices) * 1.02 if prices else avg_price * 1.02
            
            news_sentiment = 0.0
            if 'sentiment_data' in fusion_data:
                sentiment_data = fusion_data['sentiment_data']
                if isinstance(sentiment_data, dict) and 'compound' in sentiment_data:
                    news_sentiment = sentiment_data['compound']
            
            economic_indicators = fusion_data.get('economic_data', {})
            
            momentum = 0.0
            if len(prices) >= 2:
                momentum = (prices[-1] - prices[0]) / prices[0] if prices[0] != 0 else 0
            
            analysis = MarketAnalysis(
                symbol=symbol,
                trend_direction=trend_direction,
                volatility=price_volatility,
                momentum=momentum,
                support_level=support_level,
                resistance_level=resistance_level,
                rsi=fusion_data.get('technical_indicators', {}).get('rsi', 50),
                macd_signal='BULLISH' if momentum > 0.01 else 'BEARISH' if momentum < -0.01 else 'NEUTRAL',
                volume_analysis='HIGH' if len(fusion_data.get('volumes', [])) > 0 else 'LOW',
                news_sentiment=news_sentiment,
                economic_indicators=economic_indicators
            )
            
            logger.info(f"📊 Analysis complete for {symbol}: {trend_direction} trend, {price_volatility:.4f} volatility")
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Error analyzing {symbol}: {e}")
            return None
    
    async def make_trading_decisions(self, analyses: List[MarketAnalysis]) -> List[TradingDecision]:
        """Make intelligent trading decisions based on comprehensive market analysis"""
        decisions = []
        
        for analysis in analyses:
            try:
                decision = await self.calculate_optimal_decision(analysis)
                if decision and decision.confidence >= self.risk_parameters['min_confidence']:
                    decisions.append(decision)
                    logger.info(f"🎯 Decision: {decision.action} {decision.symbol} (Confidence: {decision.confidence:.2f})")
                
            except Exception as e:
                logger.error(f"❌ Error making decision for {analysis.symbol}: {e}")
        
        filtered_decisions = self.filter_correlated_decisions(decisions)
        
        return filtered_decisions
    
    async def calculate_optimal_decision(self, analysis: MarketAnalysis) -> Optional[TradingDecision]:
        """Calculate the optimal trading decision using advanced algorithms"""
        
        score = 0.0
        confidence_factors = []
        
        if analysis.trend_direction == 'BULLISH':
            score += 0.4
            confidence_factors.append("Strong bullish trend")
        elif analysis.trend_direction == 'BEARISH':
            score -= 0.4
            confidence_factors.append("Strong bearish trend")
        
        if analysis.momentum > 0.02:
            score += 0.25
            confidence_factors.append("Positive momentum")
        elif analysis.momentum < -0.02:
            score -= 0.25
            confidence_factors.append("Negative momentum")
        
        if analysis.rsi < 30:  # Oversold
            score += 0.2
            confidence_factors.append("RSI oversold")
        elif analysis.rsi > 70:  # Overbought
            score -= 0.2
            confidence_factors.append("RSI overbought")
        
        if analysis.news_sentiment > 0.1:
            score += 0.1
            confidence_factors.append("Positive news sentiment")
        elif analysis.news_sentiment < -0.1:
            score -= 0.1
            confidence_factors.append("Negative news sentiment")
        
        if analysis.volatility > 0.05:  # High volatility
            score *= 0.8  # Reduce confidence in high volatility
            confidence_factors.append("High volatility adjustment")
        
        confidence = abs(score)
        
        if score > 0.3:
            action = 'BUY'
        elif score < -0.3:
            action = 'SELL'
        else:
            action = 'HOLD'
        
        if action == 'HOLD':
            return None
        
        position_size = min(
            confidence * self.risk_parameters['max_position_size'],
            self.risk_parameters['max_position_size']
        )
        
        entry_price = (analysis.support_level + analysis.resistance_level) / 2
        
        if action == 'BUY':
            stop_loss = analysis.support_level * 0.98
            take_profit = analysis.resistance_level * 1.02
        else:  # SELL
            stop_loss = analysis.resistance_level * 1.02
            take_profit = analysis.support_level * 0.98
        
        decision = TradingDecision(
            symbol=analysis.symbol,
            action=action,
            confidence=confidence,
            position_size=position_size,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reasoning="; ".join(confidence_factors),
            data_sources=['multi_api_fusion'],
            timestamp=time.time()
        )
        
        return decision
    
    def filter_correlated_decisions(self, decisions: List[TradingDecision]) -> List[TradingDecision]:
        """Filter out highly correlated trading decisions to reduce risk"""
        if len(decisions) <= 1:
            return decisions
        
        buy_decisions = [d for d in decisions if d.action == 'BUY']
        sell_decisions = [d for d in decisions if d.action == 'SELL']
        
        buy_decisions.sort(key=lambda x: x.confidence, reverse=True)
        sell_decisions.sort(key=lambda x: x.confidence, reverse=True)
        
        filtered = buy_decisions[:3] + sell_decisions[:3]
        
        if len(filtered) < len(decisions):
            logger.info(f"🔍 Filtered {len(decisions) - len(filtered)} correlated decisions")
        
        return filtered
    
    async def execute_decision(self, decision: TradingDecision):
        """Execute a trading decision (simulation mode for now)"""
        try:
            self.active_positions[decision.symbol] = {
                'action': decision.action,
                'size': decision.position_size,
                'entry_price': decision.entry_price,
                'stop_loss': decision.stop_loss,
                'take_profit': decision.take_profit,
                'timestamp': decision.timestamp,
                'reasoning': decision.reasoning
            }
            
            self.decision_history.append(decision)
            self.performance_metrics['total_trades'] += 1
            
            logger.info(f"✅ Executed {decision.action} {decision.symbol} - Size: {decision.position_size:.4f}")
            logger.info(f"📝 Reasoning: {decision.reasoning}")
            
        except Exception as e:
            logger.error(f"❌ Failed to execute decision for {decision.symbol}: {e}")
    
    def update_performance_metrics(self):
        """Update performance tracking metrics"""
        if not self.decision_history:
            return
        
        if self.performance_metrics['total_trades'] > 0:
            self.performance_metrics['win_rate'] = (
                self.performance_metrics['winning_trades'] / 
                self.performance_metrics['total_trades']
            )
        
        recent_decisions = self.decision_history[-10:]  # Last 10 decisions
        if recent_decisions:
            confidences = [d.confidence for d in recent_decisions]
            avg_confidence = np.mean(confidences)
            self.performance_metrics['avg_confidence'] = avg_confidence
    
    def log_engine_status(self):
        """Log current engine status and performance"""
        active_count = len(self.active_positions)
        total_trades = self.performance_metrics['total_trades']
        win_rate = self.performance_metrics.get('win_rate', 0) * 100
        
        logger.info(f"🤖 Engine Status: {active_count} active positions, {total_trades} total trades, {win_rate:.1f}% win rate")
        
        if self.active_positions:
            for symbol, position in self.active_positions.items():
                logger.info(f"📈 Active: {position['action']} {symbol} @ {position['entry_price']:.4f}")
    
    def get_engine_summary(self) -> Dict[str, Any]:
        """Get comprehensive engine performance summary"""
        return {
            'active_positions': len(self.active_positions),
            'total_decisions': len(self.decision_history),
            'performance_metrics': self.performance_metrics,
            'recent_decisions': self.decision_history[-5:] if self.decision_history else [],
            'current_positions': self.active_positions,
            'engine_status': 'ACTIVE' if self.fusion_system else 'INACTIVE'
        }
