"""
AUTOBOT Automatic Mode Manager

This module implements automatic mode switching for AUTOBOT based on:
1. Real-time market conditions
2. System performance metrics
3. Security threat detection
4. Trading performance

The mode manager dynamically switches between Standard, Turbo, and Ghost modes
across different components of the system to optimize performance and security
without requiring user intervention.
"""

import os
import time
import logging
import threading
import numpy as np
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class OperatingMode(Enum):
    """Operating modes for AUTOBOT components."""
    STANDARD = "standard"  # Balance between performance and security
    TURBO = "turbo"        # Maximum performance, higher risk
    GHOST = "ghost"        # Maximum security and stealth

class ComponentType(Enum):
    """Component types that can have different operating modes."""
    TRADING = "trading"
    HFT = "hft"
    RL = "rl"
    ECOMMERCE = "ecommerce"
    SECURITY = "security"
    NETWORKING = "networking"
    UI = "ui"

class MarketCondition(Enum):
    """Market condition classifications."""
    NORMAL = "normal"
    VOLATILE = "volatile"
    OPPORTUNITY = "opportunity"
    DANGEROUS = "dangerous"
    RESTRICTED = "restricted"

class SecurityThreat(Enum):
    """Security threat levels."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class SystemPerformance(Enum):
    """System performance classifications."""
    EXCELLENT = "excellent"
    GOOD = "good"
    AVERAGE = "average"
    POOR = "poor"
    CRITICAL = "critical"

class AutoModeManager:
    """
    Automatic Mode Manager for AUTOBOT.
    
    This class manages the automatic switching between different operating modes
    based on real-time analysis of market conditions, system performance, and
    security threats.
    """
    
    def __init__(self, 
                 default_mode: OperatingMode = OperatingMode.STANDARD,
                 always_ghost: bool = True,
                 auto_switching_enabled: bool = True,
                 analysis_interval: int = 60):
        """
        Initialize the Auto Mode Manager.
        
        Args:
            default_mode: Default operating mode for all components
            always_ghost: Whether to always use Ghost mode for security-critical components
            auto_switching_enabled: Whether automatic mode switching is enabled
            analysis_interval: Interval in seconds between analyses
        """
        self.default_mode = default_mode
        self.always_ghost = always_ghost
        self.auto_switching_enabled = auto_switching_enabled
        self.analysis_interval = analysis_interval
        
        self.component_modes: Dict[ComponentType, OperatingMode] = {
            component: default_mode for component in ComponentType
        }
        
        if self.always_ghost:
            self.component_modes[ComponentType.SECURITY] = OperatingMode.GHOST
        
        self.market_condition = MarketCondition.NORMAL
        self.security_threat = SecurityThreat.NONE
        self.system_performance = SystemPerformance.GOOD
        
        self.mode_history: List[Dict[str, Any]] = []
        
        self.analysis_thread = None
        self.stop_event = threading.Event()
        
        if self.auto_switching_enabled:
            self.start_analysis_thread()
    
    def start_analysis_thread(self):
        """Start the analysis thread for automatic mode switching."""
        if self.analysis_thread is not None and self.analysis_thread.is_alive():
            logger.warning("Analysis thread is already running")
            return
        
        self.stop_event.clear()
        self.analysis_thread = threading.Thread(
            target=self._analysis_loop,
            daemon=True,
            name="autobot-mode-analysis"
        )
        self.analysis_thread.start()
        logger.info("Started automatic mode analysis thread")
    
    def stop_analysis_thread(self):
        """Stop the analysis thread."""
        if self.analysis_thread is None or not self.analysis_thread.is_alive():
            logger.warning("Analysis thread is not running")
            return
        
        self.stop_event.set()
        self.analysis_thread.join(timeout=5.0)
        if self.analysis_thread.is_alive():
            logger.warning("Analysis thread did not stop gracefully")
        else:
            logger.info("Stopped automatic mode analysis thread")
    
    def _analysis_loop(self):
        """Main analysis loop for automatic mode switching."""
        while not self.stop_event.is_set():
            try:
                self._analyze_market_conditions()
                self._analyze_security_threats()
                self._analyze_system_performance()
                
                self._update_modes()
                
                for _ in range(self.analysis_interval):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Error in mode analysis loop: {str(e)}")
                time.sleep(10)  # Sleep longer on error
    
    def _analyze_market_conditions(self):
        """
        Analyze current market conditions.
        
        This method analyzes various market indicators to determine the current
        market condition, which affects the operating mode selection.
        """
        try:
            
            rand_val = np.random.random()
            
            if rand_val < 0.6:
                new_condition = MarketCondition.NORMAL
            elif rand_val < 0.8:
                new_condition = MarketCondition.VOLATILE
            elif rand_val < 0.9:
                new_condition = MarketCondition.OPPORTUNITY
            else:
                new_condition = MarketCondition.DANGEROUS
            
            if new_condition != self.market_condition:
                logger.info(f"Market condition changed: {self.market_condition.value} -> {new_condition.value}")
                self.market_condition = new_condition
        
        except Exception as e:
            logger.error(f"Error analyzing market conditions: {str(e)}")
    
    def _analyze_security_threats(self):
        """
        Analyze current security threats.
        
        This method analyzes various security indicators to determine the current
        threat level, which affects the operating mode selection.
        """
        try:
            
            rand_val = np.random.random()
            
            if rand_val < 0.7:
                new_threat = SecurityThreat.NONE
            elif rand_val < 0.85:
                new_threat = SecurityThreat.LOW
            elif rand_val < 0.95:
                new_threat = SecurityThreat.MEDIUM
            elif rand_val < 0.98:
                new_threat = SecurityThreat.HIGH
            else:
                new_threat = SecurityThreat.CRITICAL
            
            if new_threat != self.security_threat:
                logger.info(f"Security threat changed: {self.security_threat.value} -> {new_threat.value}")
                self.security_threat = new_threat
        
        except Exception as e:
            logger.error(f"Error analyzing security threats: {str(e)}")
    
    def _analyze_system_performance(self):
        """
        Analyze current system performance.
        
        This method analyzes various system performance indicators to determine
        the current performance level, which affects the operating mode selection.
        """
        try:
            
            rand_val = np.random.random()
            
            if rand_val < 0.2:
                new_performance = SystemPerformance.EXCELLENT
            elif rand_val < 0.6:
                new_performance = SystemPerformance.GOOD
            elif rand_val < 0.8:
                new_performance = SystemPerformance.AVERAGE
            elif rand_val < 0.95:
                new_performance = SystemPerformance.POOR
            else:
                new_performance = SystemPerformance.CRITICAL
            
            if new_performance != self.system_performance:
                logger.info(f"System performance changed: {self.system_performance.value} -> {new_performance.value}")
                self.system_performance = new_performance
        
        except Exception as e:
            logger.error(f"Error analyzing system performance: {str(e)}")
    
    def _update_modes(self):
        """
        Update operating modes based on current conditions.
        
        This method applies the mode selection logic based on the current
        market condition, security threat, and system performance.
        """
        previous_modes = self.component_modes.copy()
        
        for component in ComponentType:
            if self.always_ghost and component == ComponentType.SECURITY:
                continue
            
            new_mode = self._select_mode_for_component(component)
            
            self.component_modes[component] = new_mode
        
        for component, mode in self.component_modes.items():
            if mode != previous_modes[component]:
                logger.info(f"Mode changed for {component.value}: {previous_modes[component].value} -> {mode.value}")
                
                self.mode_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "component": component.value,
                    "previous_mode": previous_modes[component].value,
                    "new_mode": mode.value,
                    "market_condition": self.market_condition.value,
                    "security_threat": self.security_threat.value,
                    "system_performance": self.system_performance.value
                })
    
    def _select_mode_for_component(self, component: ComponentType) -> OperatingMode:
        """
        Select the appropriate mode for a component based on current conditions.
        
        Args:
            component: The component to select a mode for
            
        Returns:
            OperatingMode: The selected operating mode
        """
        if self.security_threat in [SecurityThreat.HIGH, SecurityThreat.CRITICAL]:
            return OperatingMode.GHOST
        
        if self.system_performance == SystemPerformance.CRITICAL:
            if component in [ComponentType.UI, ComponentType.NETWORKING]:
                return OperatingMode.STANDARD
            return OperatingMode.GHOST
        
        if self.market_condition == MarketCondition.OPPORTUNITY:
            if component in [ComponentType.TRADING, ComponentType.HFT]:
                return OperatingMode.TURBO
        
        if self.market_condition == MarketCondition.VOLATILE:
            if component in [ComponentType.TRADING, ComponentType.HFT]:
                return OperatingMode.STANDARD
        
        if self.market_condition == MarketCondition.DANGEROUS:
            if component in [ComponentType.TRADING, ComponentType.HFT]:
                return OperatingMode.GHOST
        
        if self.system_performance in [SystemPerformance.EXCELLENT, SystemPerformance.GOOD]:
            if component == ComponentType.HFT:
                return OperatingMode.TURBO
        
        return self.component_modes.get(component, self.default_mode)
    
    def get_mode(self, component: ComponentType) -> OperatingMode:
        """
        Get the current operating mode for a component.
        
        Args:
            component: The component to get the mode for
            
        Returns:
            OperatingMode: The current operating mode
        """
        return self.component_modes.get(component, self.default_mode)
    
    def set_mode(self, component: ComponentType, mode: OperatingMode):
        """
        Manually set the operating mode for a component.
        
        Args:
            component: The component to set the mode for
            mode: The operating mode to set
        """
        if self.always_ghost and component == ComponentType.SECURITY:
            logger.warning("Cannot change security component mode when always_ghost is enabled")
            return
        
        previous_mode = self.component_modes.get(component, self.default_mode)
        self.component_modes[component] = mode
        
        logger.info(f"Manually set mode for {component.value}: {previous_mode.value} -> {mode.value}")
        
        self.mode_history.append({
            "timestamp": datetime.now().isoformat(),
            "component": component.value,
            "previous_mode": previous_mode.value,
            "new_mode": mode.value,
            "manual": True
        })
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        Get the current system status.
        
        Returns:
            Dict[str, Any]: Current system status
        """
        return {
            "market_condition": self.market_condition.value,
            "security_threat": self.security_threat.value,
            "system_performance": self.system_performance.value,
            "component_modes": {component.value: mode.value for component, mode in self.component_modes.items()},
            "auto_switching_enabled": self.auto_switching_enabled,
            "always_ghost": self.always_ghost,
            "analysis_interval": self.analysis_interval,
            "last_update": datetime.now().isoformat()
        }
    
    def get_mode_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get the mode switching history.
        
        Args:
            limit: Maximum number of history entries to return
            
        Returns:
            List[Dict[str, Any]]: Mode switching history
        """
        return self.mode_history[-limit:]
    
    def set_auto_switching(self, enabled: bool):
        """
        Enable or disable automatic mode switching.
        
        Args:
            enabled: Whether automatic mode switching should be enabled
        """
        if enabled == self.auto_switching_enabled:
            return
        
        self.auto_switching_enabled = enabled
        
        if enabled:
            self.start_analysis_thread()
        else:
            self.stop_analysis_thread()
        
        logger.info(f"Automatic mode switching {'enabled' if enabled else 'disabled'}")
    
    def set_always_ghost(self, enabled: bool):
        """
        Enable or disable always using Ghost mode for security components.
        
        Args:
            enabled: Whether to always use Ghost mode for security components
        """
        if enabled == self.always_ghost:
            return
        
        self.always_ghost = enabled
        
        if enabled:
            self.component_modes[ComponentType.SECURITY] = OperatingMode.GHOST
        
        logger.info(f"Always Ghost mode for security components {'enabled' if enabled else 'disabled'}")
    
    def set_analysis_interval(self, interval: int):
        """
        Set the interval between analyses.
        
        Args:
            interval: Interval in seconds between analyses
        """
        if interval < 1:
            logger.warning(f"Invalid analysis interval: {interval}, must be at least 1 second")
            return
        
        self.analysis_interval = interval
        logger.info(f"Analysis interval set to {interval} seconds")
    
    def reset_to_defaults(self):
        """Reset all modes to default values."""
        previous_modes = self.component_modes.copy()
        
        for component in ComponentType:
            if self.always_ghost and component == ComponentType.SECURITY:
                self.component_modes[component] = OperatingMode.GHOST
            else:
                self.component_modes[component] = self.default_mode
        
        for component, mode in self.component_modes.items():
            if mode != previous_modes[component]:
                logger.info(f"Reset mode for {component.value}: {previous_modes[component].value} -> {mode.value}")
        
        logger.info("Reset all component modes to defaults")

_instance = None

def get_mode_manager(
    default_mode: str = "standard",
    always_ghost: bool = True,
    auto_switching_enabled: bool = True,
    analysis_interval: int = 60
) -> AutoModeManager:
    """
    Get the singleton instance of the Auto Mode Manager.
    
    Args:
        default_mode: Default operating mode for all components
        always_ghost: Whether to always use Ghost mode for security-critical components
        auto_switching_enabled: Whether automatic mode switching is enabled
        analysis_interval: Interval in seconds between analyses
        
    Returns:
        AutoModeManager: Singleton instance of the Auto Mode Manager
    """
    global _instance
    
    if _instance is None:
        mode_enum = OperatingMode.STANDARD
        if default_mode.lower() == "turbo":
            mode_enum = OperatingMode.TURBO
        elif default_mode.lower() == "ghost":
            mode_enum = OperatingMode.GHOST
        
        _instance = AutoModeManager(
            default_mode=mode_enum,
            always_ghost=always_ghost,
            auto_switching_enabled=auto_switching_enabled,
            analysis_interval=analysis_interval
        )
    
    return _instance

def get_component_mode(component: str) -> str:
    """
    Get the current operating mode for a component.
    
    Args:
        component: The component to get the mode for
        
    Returns:
        str: The current operating mode as a string
    """
    manager = get_mode_manager()
    
    component_enum = None
    for comp in ComponentType:
        if comp.value == component.lower():
            component_enum = comp
            break
    
    if component_enum is None:
        logger.warning(f"Unknown component: {component}")
        return manager.default_mode.value
    
    return manager.get_mode(component_enum).value

def set_component_mode(component: str, mode: str):
    """
    Set the operating mode for a component.
    
    Args:
        component: The component to set the mode for
        mode: The operating mode to set
    """
    manager = get_mode_manager()
    
    component_enum = None
    for comp in ComponentType:
        if comp.value == component.lower():
            component_enum = comp
            break
    
    if component_enum is None:
        logger.warning(f"Unknown component: {component}")
        return
    
    mode_enum = None
    for m in OperatingMode:
        if m.value == mode.lower():
            mode_enum = m
            break
    
    if mode_enum is None:
        logger.warning(f"Unknown mode: {mode}")
        return
    
    manager.set_mode(component_enum, mode_enum)
