"""
Trading Mode Manager for AUTOBOT

This module provides functionality for managing different trading modes:
- Turbo: High risk, high reward mode that prioritizes profit over risk
- Standard: Balanced approach with moderate risk and reward
- Ghost: Stealth mode that minimizes detection risk

The mode manager automatically switches between modes based on real-time
market conditions and performance metrics.
"""

import logging
import threading
import time
from enum import Enum
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)

class TradingMode(Enum):
    """Trading mode enumeration"""
    TURBO = "turbo"
    STANDARD = "standard"
    GHOST = "ghost"

class ModeManager:
    """
    Manages trading modes and automatically switches between them
    based on real-time market conditions and performance metrics.
    """
    
    def __init__(
        self,
        autonomous_mode: bool = True,
        visible_interface: bool = True,
        default_mode: TradingMode = TradingMode.STANDARD,
        auto_switching: bool = True,
        turbo_threshold: float = 0.8,  # Market confidence threshold for turbo mode
        ghost_threshold: float = 0.3,  # Market risk threshold for ghost mode
        mode_switch_cooldown: int = 300,  # 5 minutes cooldown between mode switches
        metrics_window: int = 60  # Window size for metrics calculation (in minutes)
    ):
        """
        Initialize the mode manager.
        
        Args:
            autonomous_mode: Whether to operate in autonomous mode
            visible_interface: Whether to show detailed information in the interface
            default_mode: Default trading mode
            auto_switching: Whether to automatically switch between modes
            turbo_threshold: Confidence threshold for switching to turbo mode
            ghost_threshold: Risk threshold for switching to ghost mode
            mode_switch_cooldown: Cooldown period between mode switches (in seconds)
            metrics_window: Window size for metrics calculation (in minutes)
        """
        self.autonomous_mode = autonomous_mode
        self.visible_interface = visible_interface
        self.current_mode = default_mode
        self.auto_switching = auto_switching
        self.turbo_threshold = turbo_threshold
        self.ghost_threshold = ghost_threshold
        self.mode_switch_cooldown = mode_switch_cooldown
        self.metrics_window = metrics_window
        
        self.last_switch_time = datetime.now().timestamp()
        self.mode_history = []
        self.market_metrics = {}
        self.performance_metrics = {}
        
        self._mode_switch_callbacks = []
        self._monitoring_thread = None
        self._monitoring_active = False
        
        # if self.autonomous_mode and self.auto_switching:
        #     self._start_monitoring_thread()
        
        if self.visible_interface:
            logger.info(f"Mode Manager initialized with {self.current_mode.value} mode")
        else:
            logger.debug(f"Mode Manager initialized with {self.current_mode.value} mode")
    
    def get_current_mode(self) -> TradingMode:
        """Get the current trading mode"""
        return self.current_mode
    
    def set_mode(self, mode: TradingMode, force: bool = False) -> bool:
        """
        Set the trading mode.
        
        Args:
            mode: Trading mode to set
            force: Whether to force the mode change, ignoring cooldown
            
        Returns:
            bool: Whether the mode was changed
        """
        current_time = datetime.now().timestamp()
        
        if not force and (current_time - self.last_switch_time) < self.mode_switch_cooldown:
            if self.visible_interface:
                logger.info(f"Mode switch to {mode.value} rejected: cooldown period active")
            return False
        
        if self.current_mode == mode:
            return True
        
        old_mode = self.current_mode
        self.current_mode = mode
        self.last_switch_time = current_time
        
        self.mode_history.append({
            "timestamp": current_time,
            "old_mode": old_mode.value,
            "new_mode": mode.value,
            "forced": force
        })
        
        for callback in self._mode_switch_callbacks:
            try:
                callback(old_mode, mode)
            except Exception as e:
                logger.error(f"Error in mode switch callback: {str(e)}")
        
        if self.visible_interface:
            logger.info(f"Trading mode switched from {old_mode.value} to {mode.value}")
        else:
            logger.debug(f"Trading mode switched from {old_mode.value} to {mode.value}")
        
        return True
    
    def register_mode_switch_callback(self, callback: Callable[[TradingMode, TradingMode], None]):
        """
        Register a callback to be called when the mode changes.
        
        Args:
            callback: Function to call when the mode changes
        """
        self._mode_switch_callbacks.append(callback)
    
    def update_market_metrics(self, metrics: Dict[str, Any]):
        """
        Update market metrics used for mode switching decisions.
        
        Args:
            metrics: Dictionary of market metrics
        """
        self.market_metrics.update(metrics)
        
        if self.autonomous_mode and self.auto_switching:
            self._evaluate_mode_switch()
    
    def update_performance_metrics(self, metrics: Dict[str, Any]):
        """
        Update performance metrics used for mode switching decisions.
        
        Args:
            metrics: Dictionary of performance metrics
        """
        self.performance_metrics.update(metrics)
        
        if self.autonomous_mode and self.auto_switching:
            self._evaluate_mode_switch()
    
    def _evaluate_mode_switch(self):
        """
        Evaluate whether to switch modes based on current metrics.
        """
        current_time = datetime.now().timestamp()
        
        if (current_time - self.last_switch_time) < self.mode_switch_cooldown:
            return
        
        confidence_score = self._calculate_confidence_score()
        
        risk_score = self._calculate_risk_score()
        
        if confidence_score >= self.turbo_threshold and risk_score < 0.5:
            target_mode = TradingMode.TURBO
        elif risk_score >= self.ghost_threshold:
            target_mode = TradingMode.GHOST
        else:
            target_mode = TradingMode.STANDARD
        
        if target_mode != self.current_mode:
            self.set_mode(target_mode)
    
    def _calculate_confidence_score(self) -> float:
        """
        Calculate market confidence score based on current metrics.
        
        Returns:
            float: Confidence score (0-1)
        """
        trend_strength = self.market_metrics.get("trend_strength", 0.5)
        volume_profile = self.market_metrics.get("volume_profile", 0.5)
        volatility = self.market_metrics.get("volatility", 0.5)
        sentiment = self.market_metrics.get("sentiment", 0.5)
        profit_factor = self.performance_metrics.get("profit_factor", 1.0)
        
        norm_profit_factor = min(1.0, max(0.0, (profit_factor - 1.0) / 2.0))
        
        confidence_score = (
            0.25 * trend_strength +
            0.20 * volume_profile +
            0.15 * (1.0 - volatility) +  # Lower volatility = higher confidence
            0.15 * sentiment +
            0.25 * norm_profit_factor
        )
        
        return min(1.0, max(0.0, confidence_score))
    
    def _calculate_risk_score(self) -> float:
        """
        Calculate market risk score based on current metrics.
        
        Returns:
            float: Risk score (0-1)
        """
        volatility = self.market_metrics.get("volatility", 0.5)
        liquidity = self.market_metrics.get("liquidity", 0.5)
        correlation = self.market_metrics.get("correlation", 0.5)
        drawdown = self.performance_metrics.get("max_drawdown", 0.1)
        
        risk_score = (
            0.30 * volatility +
            0.25 * (1.0 - liquidity) +  # Lower liquidity = higher risk
            0.20 * correlation +
            0.25 * min(1.0, drawdown * 5.0)  # Scale drawdown (0-20% -> 0-1)
        )
        
        return min(1.0, max(0.0, risk_score))
    
    def _start_monitoring_thread(self):
        """
        Start the background monitoring thread for autonomous mode switching.
        """
        if self._monitoring_thread is not None and self._monitoring_thread.is_alive():
            return
        
        self._monitoring_active = True
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True
        )
        self._monitoring_thread.start()
        
        if self.visible_interface:
            logger.info("Started mode monitoring thread")
        else:
            logger.debug("Started mode monitoring thread")
    
    def _monitoring_loop(self):
        """
        Background loop for continuous mode monitoring and switching.
        """
        while self._monitoring_active:
            try:
                self._evaluate_mode_switch()
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Error in mode monitoring loop: {str(e)}")
                time.sleep(30)  # 30 seconds
    
    def stop_monitoring(self):
        """
        Stop the background monitoring thread.
        """
        self._monitoring_active = False
        
        if self.visible_interface:
            logger.info("Stopped mode monitoring thread")
        else:
            logger.debug("Stopped mode monitoring thread")
    
    def get_mode_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get the mode switch history.
        
        Args:
            limit: Maximum number of history entries to return
            
        Returns:
            List[Dict]: List of mode switch history entries
        """
        if limit is None:
            return self.mode_history
        
        return self.mode_history[-limit:]
    
    def get_mode_stats(self) -> Dict[str, Any]:
        """
        Get statistics about mode usage.
        
        Returns:
            Dict: Dictionary of mode statistics
        """
        if not self.mode_history:
            return {
                "total_switches": 0,
                "mode_distribution": {
                    TradingMode.TURBO.value: 0,
                    TradingMode.STANDARD.value: 0,
                    TradingMode.GHOST.value: 0
                },
                "average_duration": {
                    TradingMode.TURBO.value: 0,
                    TradingMode.STANDARD.value: 0,
                    TradingMode.GHOST.value: 0
                }
            }
        
        mode_durations = {
            TradingMode.TURBO.value: [],
            TradingMode.STANDARD.value: [],
            TradingMode.GHOST.value: []
        }
        
        prev_entry = None
        for entry in self.mode_history:
            if prev_entry is not None:
                mode = prev_entry["new_mode"]
                duration = entry["timestamp"] - prev_entry["timestamp"]
                mode_durations[mode].append(duration)
            
            prev_entry = entry
        
        if prev_entry is not None:
            mode = prev_entry["new_mode"]
            duration = datetime.now().timestamp() - prev_entry["timestamp"]
            mode_durations[mode].append(duration)
        
        avg_durations = {}
        for mode, durations in mode_durations.items():
            if durations:
                avg_durations[mode] = sum(durations) / len(durations)
            else:
                avg_durations[mode] = 0
        
        total_time = sum([sum(durations) for durations in mode_durations.values()])
        mode_distribution = {}
        
        if total_time > 0:
            for mode, durations in mode_durations.items():
                mode_time = sum(durations)
                mode_distribution[mode] = mode_time / total_time
        else:
            for mode in mode_durations.keys():
                mode_distribution[mode] = 0
        
        return {
            "total_switches": len(self.mode_history),
            "mode_distribution": mode_distribution,
            "average_duration": avg_durations
        }


def create_mode_manager(
    autonomous_mode: bool = True,
    visible_interface: bool = True,
    default_mode: str = "standard",
    auto_switching: bool = True
) -> ModeManager:
    """
    Create a new mode manager.
    
    Args:
        autonomous_mode: Whether to operate in autonomous mode
        visible_interface: Whether to show detailed information in the interface
        default_mode: Default trading mode ("turbo", "standard", or "ghost")
        auto_switching: Whether to automatically switch between modes
        
    Returns:
        ModeManager: New mode manager instance
    """
    mode_map = {
        "turbo": TradingMode.TURBO,
        "standard": TradingMode.STANDARD,
        "ghost": TradingMode.GHOST
    }
    
    default_mode_enum = mode_map.get(default_mode.lower(), TradingMode.STANDARD)
    
    return ModeManager(
        autonomous_mode=autonomous_mode,
        visible_interface=visible_interface,
        default_mode=default_mode_enum,
        auto_switching=auto_switching
    )
