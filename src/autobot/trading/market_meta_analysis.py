"""
Market meta-analysis module for AUTOBOT.

This module provides advanced market meta-analysis capabilities for AUTOBOT,
enabling it to analyze multiple markets simultaneously and identify
cross-market patterns and opportunities.
"""

import time
import logging
import threading
import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple, Callable, Union
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)

_meta_analysis_active = False

class MarketMetaAnalyzer:
    """
    Market meta-analyzer for AUTOBOT.
    
    This class provides advanced market meta-analysis capabilities for AUTOBOT,
    enabling it to analyze multiple markets simultaneously and identify
    cross-market patterns and opportunities.
    """
    
    def __init__(
        self,
        markets: List[str] = None,
        correlation_window: int = 100,
        volatility_window: int = 50,
        analysis_interval: float = 60.0,
        auto_analyze: bool = True,
        visible_interface: bool = True
    ):
        """
        Initialize the market meta-analyzer.
        
        Args:
            markets: List of markets to analyze
            correlation_window: Window size for correlation analysis
            volatility_window: Window size for volatility analysis
            analysis_interval: Interval in seconds between analyses
            auto_analyze: Whether to automatically analyze markets
            visible_interface: Whether to show analysis messages in the interface
        """
        self.markets = markets or []
        self.correlation_window = correlation_window
        self.volatility_window = volatility_window
        self.analysis_interval = analysis_interval
        self.auto_analyze = auto_analyze
        self.visible_interface = visible_interface
        
        self._market_data = {}
        self._correlation_matrix = {}
        self._volatility_data = {}
        self._market_regimes = {}
        self._anomalies = []
        self._opportunities = []
        self._analysis_thread = None
        self._lock = threading.Lock()
        
        for market in self.markets:
            self._market_data[market] = {
                "prices": deque(maxlen=self.correlation_window),
                "volumes": deque(maxlen=self.correlation_window),
                "timestamps": deque(maxlen=self.correlation_window),
                "last_updated": 0
            }
        
        if auto_analyze:
            self.start_analysis()
    
    def add_market(self, market: str) -> None:
        """
        Add a market to analyze.
        
        Args:
            market: Market to add
        """
        with self._lock:
            if market not in self.markets:
                self.markets.append(market)
                
                self._market_data[market] = {
                    "prices": deque(maxlen=self.correlation_window),
                    "volumes": deque(maxlen=self.correlation_window),
                    "timestamps": deque(maxlen=self.correlation_window),
                    "last_updated": 0
                }
                
                if self.visible_interface:
                    logger.info(f"Added market: {market}")
                else:
                    logger.debug(f"Added market: {market}")
    
    def remove_market(self, market: str) -> bool:
        """
        Remove a market from analysis.
        
        Args:
            market: Market to remove
            
        Returns:
            bool: Whether the market was removed
        """
        with self._lock:
            if market in self.markets:
                self.markets.remove(market)
                
                if market in self._market_data:
                    del self._market_data[market]
                
                if self.visible_interface:
                    logger.info(f"Removed market: {market}")
                else:
                    logger.debug(f"Removed market: {market}")
                
                return True
            
            return False
    
    def update_market_data(
        self,
        market: str,
        price: float,
        volume: float,
        timestamp: Optional[float] = None
    ) -> None:
        """
        Update market data.
        
        Args:
            market: Market to update
            price: Current price
            volume: Current volume
            timestamp: Current timestamp (if None, use current time)
        """
        with self._lock:
            if market not in self._market_data:
                self.add_market(market)
            
            timestamp = timestamp or time.time()
            
            self._market_data[market]["prices"].append(price)
            self._market_data[market]["volumes"].append(volume)
            self._market_data[market]["timestamps"].append(timestamp)
            self._market_data[market]["last_updated"] = timestamp
    
    def start_analysis(self) -> None:
        """Start the analysis thread."""
        global _meta_analysis_active
        
        if _meta_analysis_active:
            return
            
        _meta_analysis_active = True
        
        if self._analysis_thread is None or not self._analysis_thread.is_alive():
            self._analysis_thread = threading.Thread(
                target=self._analysis_loop,
                daemon=True
            )
            self._analysis_thread.start()
            
            if self.visible_interface:
                logger.info("Started market meta-analysis")
            else:
                logger.debug("Started market meta-analysis")
    
    def stop_analysis(self) -> None:
        """Stop the analysis thread."""
        global _meta_analysis_active
        _meta_analysis_active = False
        
        if self.visible_interface:
            logger.info("Stopped market meta-analysis")
        else:
            logger.debug("Stopped market meta-analysis")
    
    def _analysis_loop(self) -> None:
        """Background loop for analyzing markets."""
        global _meta_analysis_active
        
        while _meta_analysis_active:
            try:
                time.sleep(10)
                
                current_time = time.time()
                last_analysis = self._get_last_analysis_time()
                
                if current_time - last_analysis >= self.analysis_interval:
                    self._analyze_markets()
                
            except Exception as e:
                logger.error(f"Error in market meta-analysis: {str(e)}")
                time.sleep(60)  # Sleep longer on error
    
    def _get_last_analysis_time(self) -> float:
        """
        Get the time of the last analysis.
        
        Returns:
            float: Time of the last analysis
        """
        with self._lock:
            if not self._correlation_matrix:
                return 0
            
            return self._correlation_matrix.get("timestamp", 0)
    
    def _analyze_markets(self) -> None:
        """Analyze markets."""
        with self._lock:
            if len(self.markets) < 2:
                return
            
            if not all(len(self._market_data[market]["prices"]) > 10 for market in self.markets):
                return
            
            self._calculate_correlation_matrix()
            
            self._calculate_volatility()
            
            self._identify_market_regimes()
            
            self._detect_anomalies()
            
            self._identify_opportunities()
            
            if self.visible_interface:
                logger.info("Analyzed markets")
            else:
                logger.debug("Analyzed markets")
    
    def _calculate_correlation_matrix(self) -> None:
        """Calculate correlation matrix."""
        price_data = {}
        
        for market in self.markets:
            if len(self._market_data[market]["prices"]) > 0:
                price_data[market] = list(self._market_data[market]["prices"])
        
        if not price_data:
            return
        
        df = pd.DataFrame(price_data)
        
        corr_matrix = df.corr().to_dict()
        
        self._correlation_matrix = {
            "matrix": corr_matrix,
            "timestamp": time.time()
        }
    
    def _calculate_volatility(self) -> None:
        """Calculate volatility."""
        volatility_data = {}
        
        for market in self.markets:
            if len(self._market_data[market]["prices"]) > self.volatility_window:
                prices = list(self._market_data[market]["prices"])[-self.volatility_window:]
                
                returns = np.diff(np.log(prices))
                
                volatility = np.std(returns) * np.sqrt(252)  # Annualized
                
                volatility_data[market] = volatility
        
        self._volatility_data = {
            "volatility": volatility_data,
            "timestamp": time.time()
        }
    
    def _identify_market_regimes(self) -> None:
        """Identify market regimes."""
        regimes = {}
        
        for market in self.markets:
            if len(self._market_data[market]["prices"]) > self.volatility_window:
                prices = list(self._market_data[market]["prices"])[-self.volatility_window:]
                volumes = list(self._market_data[market]["volumes"])[-self.volatility_window:]
                
                returns = np.diff(np.log(prices))
                
                volatility = np.std(returns) * np.sqrt(252)  # Annualized
                
                avg_volume = np.mean(volumes)
                
                trend = (prices[-1] / prices[0]) - 1
                
                if volatility > 0.3:  # High volatility
                    if trend > 0.05:
                        regime = "bullish_volatile"
                    elif trend < -0.05:
                        regime = "bearish_volatile"
                    else:
                        regime = "choppy_volatile"
                else:  # Low volatility
                    if trend > 0.02:
                        regime = "bullish_stable"
                    elif trend < -0.02:
                        regime = "bearish_stable"
                    else:
                        regime = "ranging"
                
                regimes[market] = {
                    "regime": regime,
                    "volatility": volatility,
                    "trend": trend,
                    "avg_volume": avg_volume
                }
        
        self._market_regimes = {
            "regimes": regimes,
            "timestamp": time.time()
        }
    
    def _detect_anomalies(self) -> None:
        """Detect anomalies."""
        anomalies = []
        
        if self._correlation_matrix and "matrix" in self._correlation_matrix:
            corr_matrix = self._correlation_matrix["matrix"]
            
            for market1 in self.markets:
                for market2 in self.markets:
                    if market1 != market2 and market1 in corr_matrix and market2 in corr_matrix[market1]:
                        correlation = corr_matrix[market1][market2]
                        
                        if abs(correlation) < 0.2:  # Low correlation
                            anomalies.append({
                                "type": "correlation_breakdown",
                                "markets": [market1, market2],
                                "correlation": correlation,
                                "timestamp": time.time()
                            })
        
        if self._volatility_data and "volatility" in self._volatility_data:
            volatility_data = self._volatility_data["volatility"]
            
            for market, volatility in volatility_data.items():
                if volatility > 0.5:  # Very high volatility
                    anomalies.append({
                        "type": "volatility_spike",
                        "market": market,
                        "volatility": volatility,
                        "timestamp": time.time()
                    })
        
        self._anomalies = anomalies
    
    def _identify_opportunities(self) -> None:
        """Identify opportunities."""
        opportunities = []
        
        if self._correlation_matrix and "matrix" in self._correlation_matrix:
            corr_matrix = self._correlation_matrix["matrix"]
            
            for market1 in self.markets:
                for market2 in self.markets:
                    if market1 != market2 and market1 in corr_matrix and market2 in corr_matrix[market1]:
                        correlation = corr_matrix[market1][market2]
                        
                        if correlation > 0.8:  # High correlation
                            if (len(self._market_data[market1]["prices"]) > 0 and
                                len(self._market_data[market2]["prices"]) > 0):
                                price1 = self._market_data[market1]["prices"][-1]
                                price2 = self._market_data[market2]["prices"][-1]
                                
                                norm_price1 = price1 / list(self._market_data[market1]["prices"])[0]
                                norm_price2 = price2 / list(self._market_data[market2]["prices"])[0]
                                
                                divergence = abs(norm_price1 - norm_price2)
                                
                                if divergence > 0.05:  # Significant divergence
                                    opportunities.append({
                                        "type": "correlation_arbitrage",
                                        "markets": [market1, market2],
                                        "correlation": correlation,
                                        "divergence": divergence,
                                        "timestamp": time.time()
                                    })
        
        if self._market_regimes and "regimes" in self._market_regimes:
            regimes = self._market_regimes["regimes"]
            
            for market, regime_data in regimes.items():
                regime = regime_data["regime"]
                
                if regime == "bullish_volatile":
                    opportunities.append({
                        "type": "trend_following",
                        "market": market,
                        "regime": regime,
                        "direction": "long",
                        "confidence": 0.7,
                        "timestamp": time.time()
                    })
                elif regime == "bearish_volatile":
                    opportunities.append({
                        "type": "trend_following",
                        "market": market,
                        "regime": regime,
                        "direction": "short",
                        "confidence": 0.7,
                        "timestamp": time.time()
                    })
                elif regime == "ranging":
                    opportunities.append({
                        "type": "mean_reversion",
                        "market": market,
                        "regime": regime,
                        "confidence": 0.6,
                        "timestamp": time.time()
                    })
        
        self._opportunities = opportunities
    
    def get_correlation_matrix(self) -> Dict[str, Any]:
        """
        Get correlation matrix.
        
        Returns:
            Dict: Correlation matrix
        """
        with self._lock:
            return self._correlation_matrix.copy() if self._correlation_matrix else {}
    
    def get_volatility_data(self) -> Dict[str, Any]:
        """
        Get volatility data.
        
        Returns:
            Dict: Volatility data
        """
        with self._lock:
            return self._volatility_data.copy() if self._volatility_data else {}
    
    def get_market_regimes(self) -> Dict[str, Any]:
        """
        Get market regimes.
        
        Returns:
            Dict: Market regimes
        """
        with self._lock:
            return self._market_regimes.copy() if self._market_regimes else {}
    
    def get_anomalies(self) -> List[Dict[str, Any]]:
        """
        Get anomalies.
        
        Returns:
            List: Anomalies
        """
        with self._lock:
            return self._anomalies.copy() if self._anomalies else []
    
    def get_opportunities(self) -> List[Dict[str, Any]]:
        """
        Get opportunities.
        
        Returns:
            List: Opportunities
        """
        with self._lock:
            return self._opportunities.copy() if self._opportunities else []
    
    def get_market_data(self, market: str) -> Dict[str, Any]:
        """
        Get market data.
        
        Args:
            market: Market to get data for
            
        Returns:
            Dict: Market data
        """
        with self._lock:
            if market not in self._market_data:
                return {}
            
            return {
                "prices": list(self._market_data[market]["prices"]),
                "volumes": list(self._market_data[market]["volumes"]),
                "timestamps": list(self._market_data[market]["timestamps"]),
                "last_updated": self._market_data[market]["last_updated"]
            }
    
    def get_all_market_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all market data.
        
        Returns:
            Dict: All market data
        """
        with self._lock:
            return {
                market: {
                    "prices": list(data["prices"]),
                    "volumes": list(data["volumes"]),
                    "timestamps": list(data["timestamps"]),
                    "last_updated": data["last_updated"]
                }
                for market, data in self._market_data.items()
            }
    
    def get_analysis_summary(self) -> Dict[str, Any]:
        """
        Get analysis summary.
        
        Returns:
            Dict: Analysis summary
        """
        with self._lock:
            return {
                "markets": self.markets,
                "correlation_matrix": self._correlation_matrix.get("matrix", {}),
                "volatility_data": self._volatility_data.get("volatility", {}),
                "market_regimes": self._market_regimes.get("regimes", {}),
                "anomalies": self._anomalies,
                "opportunities": self._opportunities,
                "last_analysis": self._get_last_analysis_time()
            }

def create_market_meta_analyzer(
    markets: List[str] = None,
    auto_analyze: bool = True,
    visible_interface: bool = True
) -> MarketMetaAnalyzer:
    """
    Create and return a market meta-analyzer.
    
    Args:
        markets: List of markets to analyze
        auto_analyze: Whether to automatically analyze markets
        visible_interface: Whether to show analysis messages in the interface
        
    Returns:
        MarketMetaAnalyzer: New market meta-analyzer instance
    """
    return MarketMetaAnalyzer(
        markets=markets,
        auto_analyze=auto_analyze,
        visible_interface=visible_interface
    )
