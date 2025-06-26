"""
Market Manipulation Detector for AUTOBOT

This module provides functionality for detecting various forms of market manipulation:
- Pump and Dump schemes
- Wash Trading
- Spoofing
- Layering
- Quote Stuffing

The detector operates in the background and alerts the trading system when
manipulation is detected, allowing for appropriate risk management actions.
"""

import logging
import threading
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import numpy as np
from collections import deque

logger = logging.getLogger(__name__)

class ManipulationEvent:
    """Represents a detected market manipulation event"""
    
    def __init__(
        self,
        event_type: str,
        symbol: str,
        confidence: float,
        timestamp: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize a manipulation event.
        
        Args:
            event_type: Type of manipulation event
            symbol: Trading pair symbol
            confidence: Confidence score (0-1)
            timestamp: Event timestamp
            details: Additional event details
        """
        self.event_type = event_type
        self.symbol = symbol
        self.confidence = confidence
        self.timestamp = timestamp or datetime.now().timestamp()
        self.details = details or {}
        self.id = f"{event_type}_{symbol}_{int(self.timestamp)}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary"""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "symbol": self.symbol,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "details": self.details
        }


class MarketManipulationDetector:
    """
    Detector for various forms of market manipulation.
    
    Operates in the background and alerts the trading system when
    manipulation is detected, allowing for appropriate risk management actions.
    """
    
    def __init__(
        self,
        autonomous_mode: bool = True,
        visible_interface: bool = True,
        detection_interval: int = 60,  # 1 minute
        confidence_threshold: float = 0.7,
        window_size: int = 24,  # 24 hours for daily patterns
        alert_cooldown: int = 300  # 5 minutes
    ):
        """
        Initialize the market manipulation detector.
        
        Args:
            autonomous_mode: Whether to operate in autonomous mode
            visible_interface: Whether to show detailed information in the interface
            detection_interval: Interval between detection runs (in seconds)
            confidence_threshold: Threshold for alerting (0-1)
            window_size: Window size for pattern detection (in hours)
            alert_cooldown: Cooldown period between alerts for the same symbol (in seconds)
        """
        self.autonomous_mode = autonomous_mode
        self.visible_interface = visible_interface
        self.detection_interval = detection_interval
        self.confidence_threshold = confidence_threshold
        self.window_size = window_size
        self.alert_cooldown = alert_cooldown
        
        self.market_data = {}
        self.order_book_snapshots = {}
        self.trade_history = {}
        self.volume_profiles = {}
        
        self.detected_events = []
        self.last_alert_times = {}
        
        self._alert_callbacks = []
        self._detection_thread = None
        self._detection_active = False
        
        if self.autonomous_mode:
            self._start_detection_thread()
    
    def update_market_data(self, symbol: str, data: Dict[str, Any]):
        """
        Update market data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            data: Market data dictionary
        """
        if symbol not in self.market_data:
            self.market_data[symbol] = []
        
        data["timestamp"] = data.get("timestamp", datetime.now().timestamp())
        self.market_data[symbol].append(data)
        
        max_data_points = self.window_size * 60  # 1 data point per minute
        if len(self.market_data[symbol]) > max_data_points:
            self.market_data[symbol] = self.market_data[symbol][-max_data_points:]
    
    def update_order_book(self, symbol: str, order_book: Dict[str, Any]):
        """
        Update order book data for a symbol.
        
        Args:
            symbol: Trading pair symbol
            order_book: Order book data
        """
        if symbol not in self.order_book_snapshots:
            self.order_book_snapshots[symbol] = deque(maxlen=100)  # Keep last 100 snapshots
        
        snapshot = {
            "timestamp": datetime.now().timestamp(),
            "bids": order_book.get("bids", []),
            "asks": order_book.get("asks", [])
        }
        
        self.order_book_snapshots[symbol].append(snapshot)
    
    def update_trades(self, symbol: str, trades: List[Dict[str, Any]]):
        """
        Update trade history for a symbol.
        
        Args:
            symbol: Trading pair symbol
            trades: List of trades
        """
        if symbol not in self.trade_history:
            self.trade_history[symbol] = deque(maxlen=1000)  # Keep last 1000 trades
        
        for trade in trades:
            self.trade_history[symbol].append(trade)
    
    def register_alert_callback(self, callback):
        """
        Register a callback to be called when manipulation is detected.
        
        Args:
            callback: Function to call when manipulation is detected
        """
        self._alert_callbacks.append(callback)
    
    def _start_detection_thread(self):
        """
        Start the background detection thread.
        """
        if self._detection_thread is not None and self._detection_thread.is_alive():
            return
        
        self._detection_active = True
        self._detection_thread = threading.Thread(
            target=self._detection_loop,
            daemon=True
        )
        self._detection_thread.start()
        
        if self.visible_interface:
            logger.info("Started market manipulation detection thread")
        else:
            logger.debug("Started market manipulation detection thread")
    
    def _detection_loop(self):
        """
        Background loop for continuous manipulation detection.
        """
        while self._detection_active:
            try:
                for symbol in self.market_data.keys():
                    self._check_pump_and_dump(symbol)
                    self._check_wash_trading(symbol)
                    self._check_spoofing(symbol)
                
                time.sleep(self.detection_interval)
                
            except Exception as e:
                logger.error(f"Error in manipulation detection loop: {str(e)}")
                time.sleep(30)  # 30 seconds
    
    def _check_pump_and_dump(self, symbol: str):
        """
        Check for pump and dump patterns.
        
        Args:
            symbol: Trading pair symbol
        """
        if symbol not in self.market_data or len(self.market_data[symbol]) < 60:
            return
        
        recent_data = self.market_data[symbol][-60:]  # Last hour
        
        prices = [d.get("close", d.get("price", 0)) for d in recent_data]
        volumes = [d.get("volume", 0) for d in recent_data]
        
        if not prices or not volumes:
            return
        
        price_change = (prices[-1] / prices[0] - 1) * 100  # Percentage
        volume_change = (volumes[-1] / max(1, np.mean(volumes[:-10])) - 1) * 100  # Percentage
        
        if price_change > 10 and volume_change > 200:
            confidence = min(1.0, (price_change / 20) * (volume_change / 400))
            
            if confidence >= self.confidence_threshold:
                self._create_alert("pump_pattern", symbol, confidence, {
                    "price_change": price_change,
                    "volume_change": volume_change,
                    "timeframe": "1h"
                })
        
        if len(prices) >= 30:
            recent_high = max(prices[-30:])
            current_price = prices[-1]
            drop_percentage = (recent_high - current_price) / recent_high * 100
            
            if drop_percentage > 15:
                confidence = min(1.0, drop_percentage / 30)
                
                if confidence >= self.confidence_threshold:
                    self._create_alert("dump_pattern", symbol, confidence, {
                        "drop_percentage": drop_percentage,
                        "timeframe": "recent"
                    })
    
    def _check_wash_trading(self, symbol: str):
        """
        Check for wash trading patterns.
        
        Args:
            symbol: Trading pair symbol
        """
        if symbol not in self.trade_history or len(self.trade_history[symbol]) < 100:
            return
        
        recent_trades = list(self.trade_history[symbol])[-100:]
        
        size_counts = {}
        for trade in recent_trades:
            size = trade.get("amount", 0)
            rounded_size = round(size, 6)  # Round to handle small variations
            
            if rounded_size not in size_counts:
                size_counts[rounded_size] = 0
            
            size_counts[rounded_size] += 1
        
        repeated_sizes = [size for size, count in size_counts.items() if count >= 5]
        
        if repeated_sizes:
            repeated_volume = sum([size * size_counts[size] for size in repeated_sizes])
            total_volume = sum([trade.get("amount", 0) for trade in recent_trades])
            
            if total_volume > 0:
                repeated_percentage = repeated_volume / total_volume * 100
                
                if repeated_percentage > 40:
                    confidence = min(1.0, repeated_percentage / 80)
                    
                    if confidence >= self.confidence_threshold:
                        self._create_alert("wash_trading", symbol, confidence, {
                            "repeated_percentage": repeated_percentage,
                            "repeated_sizes": repeated_sizes[:5]  # Show top 5 repeated sizes
                        })
    
    def _check_spoofing(self, symbol: str):
        """
        Check for spoofing patterns.
        
        Args:
            symbol: Trading pair symbol
        """
        if symbol not in self.order_book_snapshots or len(self.order_book_snapshots[symbol]) < 10:
            return
        
        recent_snapshots = list(self.order_book_snapshots[symbol])[-10:]
        
        for side in ["bids", "asks"]:
            large_orders_appeared = []
            large_orders_disappeared = []
            
            for i in range(1, len(recent_snapshots)):
                prev_snapshot = recent_snapshots[i-1]
                curr_snapshot = recent_snapshots[i]
                
                prev_orders = prev_snapshot.get(side, [])
                curr_orders = curr_snapshot.get(side, [])
                
                prev_dict = {order[0]: order[1] for order in prev_orders}
                curr_dict = {order[0]: order[1] for order in curr_orders}
                
                for price, size in curr_dict.items():
                    if price not in prev_dict and size > 10:  # Arbitrary threshold
                        large_orders_appeared.append((price, size))
                
                for price, size in prev_dict.items():
                    if price not in curr_dict and size > 10:  # Arbitrary threshold
                        large_orders_disappeared.append((price, size))
            
            if large_orders_appeared and large_orders_disappeared:
                confidence = min(1.0, len(large_orders_disappeared) / 10)
                
                if confidence >= self.confidence_threshold:
                    self._create_alert("spoofing", symbol, confidence, {
                        "side": side,
                        "disappeared_count": len(large_orders_disappeared)
                    })
    
    def _create_alert(self, event_type: str, symbol: str, confidence: float, details: Dict[str, Any]):
        """
        Create a manipulation alert.
        
        Args:
            event_type: Type of manipulation event
            symbol: Trading pair symbol
            confidence: Confidence score (0-1)
            details: Additional event details
        """
        current_time = datetime.now().timestamp()
        
        alert_key = f"{event_type}_{symbol}"
        if alert_key in self.last_alert_times:
            time_since_last = current_time - self.last_alert_times[alert_key]
            if time_since_last < self.alert_cooldown:
                return
        
        event = ManipulationEvent(event_type, symbol, confidence, current_time, details)
        self.detected_events.append(event)
        self.last_alert_times[alert_key] = current_time
        
        if self.visible_interface:
            logger.warning(f"Market manipulation detected: {event_type} on {symbol} (confidence: {confidence:.2f})")
        else:
            logger.info(f"Market manipulation detected: {event_type} on {symbol} (confidence: {confidence:.2f})")
        
        for callback in self._alert_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Error in manipulation alert callback: {str(e)}")
    
    def get_recent_events(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get recent manipulation events.
        
        Args:
            limit: Maximum number of events to return
            
        Returns:
            List[Dict]: List of recent events
        """
        events = sorted(self.detected_events, key=lambda e: e.timestamp, reverse=True)
        
        if limit is not None:
            events = events[:limit]
        
        return [event.to_dict() for event in events]
    
    def stop_detection(self):
        """
        Stop the background detection thread.
        """
        self._detection_active = False
        
        if self.visible_interface:
            logger.info("Stopped market manipulation detection thread")
        else:
            logger.debug("Stopped market manipulation detection thread")


def create_manipulation_detector(
    autonomous_mode: bool = True,
    visible_interface: bool = True
) -> MarketManipulationDetector:
    """
    Create a new market manipulation detector.
    
    Args:
        autonomous_mode: Whether to operate in autonomous mode
        visible_interface: Whether to show detailed information in the interface
        
    Returns:
        MarketManipulationDetector: New detector instance
    """
    return MarketManipulationDetector(
        autonomous_mode=autonomous_mode,
        visible_interface=visible_interface
    )
