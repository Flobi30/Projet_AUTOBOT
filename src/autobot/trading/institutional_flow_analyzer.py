"""
Institutional Order Flow Analyzer for AUTOBOT

This module provides functionality for analyzing institutional order flow
and dark pool activity to predict market movements. It detects large block
trades, unusual options activity, and dark pool transactions to identify
potential market-moving events before they impact public markets.
"""

import logging
import threading
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import numpy as np
from collections import deque

logger = logging.getLogger(__name__)

class InstitutionalSignal:
    """Represents a detected institutional trading signal"""
    
    def __init__(
        self,
        signal_type: str,
        symbol: str,
        direction: str,
        strength: float,
        timestamp: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize an institutional signal.
        
        Args:
            signal_type: Type of signal (e.g., "dark_pool", "block_trade", "options_flow")
            symbol: Trading pair symbol
            direction: Signal direction ("bullish" or "bearish")
            strength: Signal strength (0-1)
            timestamp: Signal timestamp
            details: Additional signal details
        """
        self.signal_type = signal_type
        self.symbol = symbol
        self.direction = direction
        self.strength = strength
        self.timestamp = timestamp or datetime.now().timestamp()
        self.details = details or {}
        self.id = f"{signal_type}_{symbol}_{int(self.timestamp)}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to dictionary"""
        return {
            "id": self.id,
            "signal_type": self.signal_type,
            "symbol": self.symbol,
            "direction": self.direction,
            "strength": self.strength,
            "timestamp": self.timestamp,
            "details": self.details
        }


class InstitutionalFlowAnalyzer:
    """
    Analyzer for institutional order flow and dark pool activity.
    
    Detects large block trades, unusual options activity, and dark pool
    transactions to identify potential market-moving events before they
    impact public markets.
    """
    
    def __init__(
        self,
        autonomous_mode: bool = True,
        visible_interface: bool = True,
        analysis_interval: int = 60,  # 1 minute
        signal_threshold: float = 0.6,
        window_size: int = 24,  # 24 hours for daily patterns
        signal_cooldown: int = 300  # 5 minutes
    ):
        """
        Initialize the institutional flow analyzer.
        
        Args:
            autonomous_mode: Whether to operate in autonomous mode
            visible_interface: Whether to show detailed information in the interface
            analysis_interval: Interval between analysis runs (in seconds)
            signal_threshold: Threshold for signaling (0-1)
            window_size: Window size for pattern detection (in hours)
            signal_cooldown: Cooldown period between signals for the same symbol (in seconds)
        """
        self.autonomous_mode = autonomous_mode
        self.visible_interface = visible_interface
        self.analysis_interval = analysis_interval
        self.signal_threshold = signal_threshold
        self.window_size = window_size
        self.signal_cooldown = signal_cooldown
        
        self.dark_pool_data = {}
        self.block_trades = {}
        self.options_flow = {}
        self.tape_data = {}
        
        self.detected_signals = []
        self.last_signal_times = {}
        
        self._signal_callbacks = []
        self._analysis_thread = None
        self._analysis_active = False
        
        # if self.autonomous_mode:
        #     self._start_analysis_thread()
    
    def update_dark_pool_data(self, symbol: str, data: Dict[str, Any]):
        """
        Update dark pool data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            data: Dark pool data dictionary
        """
        if symbol not in self.dark_pool_data:
            self.dark_pool_data[symbol] = []
        
        data["timestamp"] = data.get("timestamp", datetime.now().timestamp())
        self.dark_pool_data[symbol].append(data)
        
        max_data_points = self.window_size * 60  # 1 data point per minute
        if len(self.dark_pool_data[symbol]) > max_data_points:
            self.dark_pool_data[symbol] = self.dark_pool_data[symbol][-max_data_points:]
    
    def update_block_trade(self, symbol: str, trade: Dict[str, Any]):
        """
        Update block trade data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            trade: Block trade data
        """
        if symbol not in self.block_trades:
            self.block_trades[symbol] = []
        
        trade["timestamp"] = trade.get("timestamp", datetime.now().timestamp())
        self.block_trades[symbol].append(trade)
        
        max_trades = 1000
        if len(self.block_trades[symbol]) > max_trades:
            self.block_trades[symbol] = self.block_trades[symbol][-max_trades:]
    
    def update_options_flow(self, symbol: str, data: Dict[str, Any]):
        """
        Update options flow data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            data: Options flow data
        """
        if symbol not in self.options_flow:
            self.options_flow[symbol] = []
        
        data["timestamp"] = data.get("timestamp", datetime.now().timestamp())
        self.options_flow[symbol].append(data)
        
        max_data_points = 1000
        if len(self.options_flow[symbol]) > max_data_points:
            self.options_flow[symbol] = self.options_flow[symbol][-max_data_points:]
    
    def update_tape_data(self, symbol: str, data: Dict[str, Any]):
        """
        Update time and sales (tape) data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            data: Tape data
        """
        if symbol not in self.tape_data:
            self.tape_data[symbol] = deque(maxlen=10000)  # Keep last 10000 trades
        
        data["timestamp"] = data.get("timestamp", datetime.now().timestamp())
        self.tape_data[symbol].append(data)
    
    def register_signal_callback(self, callback):
        """
        Register a callback to be called when a signal is detected.
        
        Args:
            callback: Function to call when a signal is detected
        """
        self._signal_callbacks.append(callback)
    
    def _start_analysis_thread(self):
        """
        Start the background analysis thread.
        """
        if self._analysis_thread is not None and self._analysis_thread.is_alive():
            return
        
        self._analysis_active = True
        self._analysis_thread = threading.Thread(
            target=self._analysis_loop,
            daemon=True
        )
        self._analysis_thread.start()
        
        if self.visible_interface:
            logger.info("Started institutional flow analysis thread")
        else:
            logger.debug("Started institutional flow analysis thread")
    
    def _analysis_loop(self):
        """
        Background loop for continuous institutional flow analysis.
        """
        while self._analysis_active:
            try:
                for symbol in self.dark_pool_data.keys():
                    self._analyze_dark_pool(symbol)
                
                for symbol in self.block_trades.keys():
                    self._analyze_block_trades(symbol)
                
                for symbol in self.options_flow.keys():
                    self._analyze_options_flow(symbol)
                
                time.sleep(self.analysis_interval)
                
            except Exception as e:
                logger.error(f"Error in institutional flow analysis loop: {str(e)}")
                time.sleep(30)  # 30 seconds
    
    def _analyze_dark_pool(self, symbol: str):
        """
        Analyze dark pool data for a symbol.
        
        Args:
            symbol: Trading pair symbol
        """
        if symbol not in self.dark_pool_data or len(self.dark_pool_data[symbol]) < 10:
            return
        
        recent_data = self.dark_pool_data[symbol][-60:]  # Last hour
        
        total_volume = sum([d.get("volume", 0) for d in recent_data])
        
        if total_volume == 0:
            return
        
        buy_volume = sum([d.get("volume", 0) for d in recent_data if d.get("side") == "buy"])
        sell_volume = sum([d.get("volume", 0) for d in recent_data if d.get("side") == "sell"])
        
        if buy_volume + sell_volume == 0:
            return
        
        buy_percentage = buy_volume / (buy_volume + sell_volume) * 100
        
        if buy_percentage > 60:  # Bullish signal
            direction = "bullish"
            strength = min(1.0, (buy_percentage - 60) / 30)  # Scale 60-90% to 0-1
        elif buy_percentage < 40:  # Bearish signal
            direction = "bearish"
            strength = min(1.0, (40 - buy_percentage) / 30)  # Scale 40-10% to 0-1
        else:
            return  # No strong signal
        
        if strength >= self.signal_threshold:
            self._create_signal("dark_pool", symbol, direction, strength, {
                "buy_percentage": buy_percentage,
                "total_volume": total_volume,
                "timeframe": "1h"
            })
    
    def _analyze_block_trades(self, symbol: str):
        """
        Analyze block trades for a symbol.
        
        Args:
            symbol: Trading pair symbol
        """
        if symbol not in self.block_trades or len(self.block_trades[symbol]) < 5:
            return
        
        current_time = datetime.now().timestamp()
        recent_trades = [
            t for t in self.block_trades[symbol]
            if current_time - t.get("timestamp", 0) < 3600  # Last hour
        ]
        
        if not recent_trades:
            return
        
        total_volume = sum([t.get("volume", 0) for t in recent_trades])
        
        if total_volume == 0:
            return
        
        buy_volume = sum([t.get("volume", 0) for t in recent_trades if t.get("side") == "buy"])
        sell_volume = sum([t.get("volume", 0) for t in recent_trades if t.get("side") == "sell"])
        
        if buy_volume + sell_volume == 0:
            return
        
        buy_percentage = buy_volume / (buy_volume + sell_volume) * 100
        
        avg_trade_size = total_volume / len(recent_trades)
        
        if buy_percentage > 60:  # Bullish signal
            direction = "bullish"
            strength = min(1.0, (buy_percentage - 60) / 30)  # Scale 60-90% to 0-1
        elif buy_percentage < 40:  # Bearish signal
            direction = "bearish"
            strength = min(1.0, (40 - buy_percentage) / 30)  # Scale 40-10% to 0-1
        else:
            return  # No strong signal
        
        size_factor = min(1.0, avg_trade_size / 1000000)  # Scale by trade size (arbitrary threshold)
        strength = (strength + size_factor) / 2  # Average with size factor
        
        if strength >= self.signal_threshold:
            self._create_signal("block_trade", symbol, direction, strength, {
                "buy_percentage": buy_percentage,
                "total_volume": total_volume,
                "avg_trade_size": avg_trade_size,
                "trade_count": len(recent_trades),
                "timeframe": "1h"
            })
    
    def _analyze_options_flow(self, symbol: str):
        """
        Analyze options flow for a symbol.
        
        Args:
            symbol: Trading pair symbol
        """
        if symbol not in self.options_flow or len(self.options_flow[symbol]) < 10:
            return
        
        current_time = datetime.now().timestamp()
        recent_data = [
            d for d in self.options_flow[symbol]
            if current_time - d.get("timestamp", 0) < 3600  # Last hour
        ]
        
        if not recent_data:
            return
        
        call_volume = sum([d.get("volume", 0) for d in recent_data if d.get("option_type") == "call"])
        put_volume = sum([d.get("volume", 0) for d in recent_data if d.get("option_type") == "put"])
        
        if call_volume + put_volume == 0:
            return
        
        call_put_ratio = call_volume / max(1, put_volume)
        
        call_premium = sum([d.get("premium", 0) for d in recent_data if d.get("option_type") == "call"])
        put_premium = sum([d.get("premium", 0) for d in recent_data if d.get("option_type") == "put"])
        
        if call_put_ratio > 2.0:  # Bullish signal
            direction = "bullish"
            strength = min(1.0, (call_put_ratio - 2.0) / 3.0)  # Scale 2-5 to 0-1
        elif call_put_ratio < 0.5:  # Bearish signal
            direction = "bearish"
            strength = min(1.0, (0.5 - call_put_ratio) / 0.4)  # Scale 0.5-0.1 to 0-1
        else:
            return  # No strong signal
        
        if call_premium + put_premium > 0:
            premium_ratio = call_premium / max(1, put_premium)
            premium_strength = 0.0
            
            if direction == "bullish" and premium_ratio > 2.0:
                premium_strength = min(1.0, (premium_ratio - 2.0) / 3.0)
            elif direction == "bearish" and premium_ratio < 0.5:
                premium_strength = min(1.0, (0.5 - premium_ratio) / 0.4)
            
            strength = (strength + premium_strength) / 2
        
        if strength >= self.signal_threshold:
            self._create_signal("options_flow", symbol, direction, strength, {
                "call_put_ratio": call_put_ratio,
                "call_volume": call_volume,
                "put_volume": put_volume,
                "call_premium": call_premium,
                "put_premium": put_premium,
                "timeframe": "1h"
            })
    
    def _create_signal(self, signal_type: str, symbol: str, direction: str, strength: float, details: Dict[str, Any]):
        """
        Create an institutional signal.
        
        Args:
            signal_type: Type of signal
            symbol: Trading pair symbol
            direction: Signal direction
            strength: Signal strength
            details: Additional signal details
        """
        current_time = datetime.now().timestamp()
        
        signal_key = f"{signal_type}_{symbol}"
        if signal_key in self.last_signal_times:
            time_since_last = current_time - self.last_signal_times[signal_key]
            if time_since_last < self.signal_cooldown:
                return
        
        signal = InstitutionalSignal(signal_type, symbol, direction, strength, current_time, details)
        self.detected_signals.append(signal)
        self.last_signal_times[signal_key] = current_time
        
        if self.visible_interface:
            logger.info(f"Institutional signal detected: {signal_type} on {symbol} ({direction}, strength: {strength:.2f})")
        else:
            logger.debug(f"Institutional signal detected: {signal_type} on {symbol} ({direction}, strength: {strength:.2f})")
        
        for callback in self._signal_callbacks:
            try:
                callback(signal)
            except Exception as e:
                logger.error(f"Error in institutional signal callback: {str(e)}")
    
    def get_recent_signals(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get recent institutional signals.
        
        Args:
            limit: Maximum number of signals to return
            
        Returns:
            List[Dict]: List of recent signals
        """
        signals = sorted(self.detected_signals, key=lambda s: s.timestamp, reverse=True)
        
        if limit is not None:
            signals = signals[:limit]
        
        return [signal.to_dict() for signal in signals]
    
    def get_symbol_signals(self, symbol: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get signals for a specific symbol.
        
        Args:
            symbol: Trading pair symbol
            limit: Maximum number of signals to return
            
        Returns:
            List[Dict]: List of signals for the symbol
        """
        signals = [s for s in self.detected_signals if s.symbol == symbol]
        signals = sorted(signals, key=lambda s: s.timestamp, reverse=True)
        
        if limit is not None:
            signals = signals[:limit]
        
        return [signal.to_dict() for signal in signals]
    
    def get_signal_stats(self) -> Dict[str, Any]:
        """
        Get statistics about institutional signals.
        
        Returns:
            Dict: Dictionary of signal statistics
        """
        total_signals = len(self.detected_signals)
        
        if total_signals == 0:
            return {
                "total_signals": 0,
                "bullish_count": 0,
                "bearish_count": 0,
                "bullish_percentage": 0,
                "bearish_percentage": 0,
                "signal_types": {},
                "symbols": {}
            }
        
        bullish_count = len([s for s in self.detected_signals if s.direction == "bullish"])
        bearish_count = len([s for s in self.detected_signals if s.direction == "bearish"])
        
        signal_types = {}
        for signal in self.detected_signals:
            if signal.signal_type not in signal_types:
                signal_types[signal.signal_type] = 0
            
            signal_types[signal.signal_type] += 1
        
        symbols = {}
        for signal in self.detected_signals:
            if signal.symbol not in symbols:
                symbols[signal.symbol] = 0
            
            symbols[signal.symbol] += 1
        
        return {
            "total_signals": total_signals,
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "bullish_percentage": bullish_count / total_signals * 100,
            "bearish_percentage": bearish_count / total_signals * 100,
            "signal_types": signal_types,
            "symbols": symbols
        }
    
    def stop_analysis(self):
        """
        Stop the background analysis thread.
        """
        self._analysis_active = False
        
        if self.visible_interface:
            logger.info("Stopped institutional flow analysis thread")
        else:
            logger.debug("Stopped institutional flow analysis thread")


def create_institutional_flow_analyzer(
    autonomous_mode: bool = True,
    visible_interface: bool = True
) -> InstitutionalFlowAnalyzer:
    """
    Create a new institutional flow analyzer.
    
    Args:
        autonomous_mode: Whether to operate in autonomous mode
        visible_interface: Whether to show detailed information in the interface
        
    Returns:
        InstitutionalFlowAnalyzer: New analyzer instance
    """
    return InstitutionalFlowAnalyzer(
        autonomous_mode=autonomous_mode,
        visible_interface=visible_interface
    )
