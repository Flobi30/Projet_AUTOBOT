"""
Anomaly Detection Agent for AUTOBOT

This agent uses advanced machine learning techniques to detect market anomalies
and trading opportunities in real-time.
"""

import logging
import numpy as np
import time
from typing import Dict, List, Any, Optional, Tuple, Union
import torch
import torch.nn as nn
from datetime import datetime
import threading
import queue
import pandas as pd
from dataclasses import dataclass

from autobot.prediction.features import extract_features
from autobot.trading.strategy import Strategy

logger = logging.getLogger(__name__)

@dataclass
class AnomalyEvent:
    """Represents a detected market anomaly event"""
    symbol: str
    timestamp: float
    anomaly_type: str
    confidence: float
    features: Dict[str, float]
    action: Optional[str] = None
    expected_profit: Optional[float] = None
    duration_estimate: Optional[int] = None


class AnomalyDetector(nn.Module):
    """Neural network for detecting market anomalies"""
    
    def __init__(self, input_dim: int, hidden_dim: int = 128):
        """
        Initialize the anomaly detector model
        
        Args:
            input_dim: Dimension of input features
            hidden_dim: Dimension of hidden layers
        """
        super(AnomalyDetector, self).__init__()
        
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LeakyReLU(0.2),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.LeakyReLU(0.2),
            nn.Linear(hidden_dim // 2, hidden_dim // 4),
            nn.LeakyReLU(0.2)
        )
        
        self.decoder = nn.Sequential(
            nn.Linear(hidden_dim // 4, hidden_dim // 2),
            nn.LeakyReLU(0.2),
            nn.Linear(hidden_dim // 2, hidden_dim),
            nn.LeakyReLU(0.2),
            nn.Linear(hidden_dim, input_dim)
        )
        
        self.apply(self._init_weights)
    
    def _init_weights(self, module):
        """Initialize network weights"""
        if isinstance(module, nn.Linear):
            nn.init.xavier_normal_(module.weight)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through the network
        
        Args:
            x: Input tensor
            
        Returns:
            Reconstructed input tensor
        """
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded
    
    def get_reconstruction_error(self, x: torch.Tensor) -> torch.Tensor:
        """
        Calculate reconstruction error for anomaly detection
        
        Args:
            x: Input tensor
            
        Returns:
            Reconstruction error tensor
        """
        x_hat = self.forward(x)
        error = torch.mean((x - x_hat) ** 2, dim=1)
        return error


class AnomalyDetectionAgent:
    """
    Agent that detects market anomalies and trading opportunities
    using advanced machine learning techniques.
    """
    
    def __init__(
        self,
        symbols: List[str],
        feature_window: int = 100,
        update_interval: int = 60,
        anomaly_threshold: float = 3.0,
        device: str = "auto"
    ):
        """
        Initialize the anomaly detection agent
        
        Args:
            symbols: List of trading symbols to monitor
            feature_window: Number of data points to use for feature extraction
            update_interval: Interval in seconds between model updates
            anomaly_threshold: Threshold for anomaly detection (standard deviations)
            device: Device to use for model inference
        """
        self.symbols = symbols
        self.feature_window = feature_window
        self.update_interval = update_interval
        self.anomaly_threshold = anomaly_threshold
        
        if device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)
        
        logger.info(f"Anomaly Detection Agent initialized with device: {self.device}")
        
        self.data_buffers = {symbol: [] for symbol in symbols}
        self.models = {}
        self.baseline_errors = {}
        self.error_stds = {}
        
        self.event_queue = queue.Queue()
        self.running = True
        
        self.update_thread = threading.Thread(target=self._update_models_loop)
        self.update_thread.daemon = True
        self.update_thread.start()
    
    def add_data_point(self, symbol: str, data: Dict[str, float]):
        """
        Add a new data point for a symbol
        
        Args:
            symbol: Trading symbol
            data: Market data point
        """
        if symbol not in self.symbols:
            logger.warning(f"Symbol {symbol} not in monitored symbols")
            return
        
        self.data_buffers[symbol].append(data)
        
        if len(self.data_buffers[symbol]) > self.feature_window * 2:
            self.data_buffers[symbol] = self.data_buffers[symbol][-self.feature_window * 2:]
        
        if symbol in self.models and len(self.data_buffers[symbol]) >= self.feature_window:
            self._check_anomaly(symbol)
    
    def _check_anomaly(self, symbol: str):
        """
        Check for anomalies in the latest data for a symbol
        
        Args:
            symbol: Trading symbol
        """
        if len(self.data_buffers[symbol]) < self.feature_window:
            return
        
        data_window = self.data_buffers[symbol][-self.feature_window:]
        features = extract_features(data_window)
        
        if features is None or len(features) == 0:
            return
        
        feature_tensor = torch.FloatTensor([list(features.values())]).to(self.device)
        
        with torch.no_grad():
            error = self.models[symbol].get_reconstruction_error(feature_tensor).item()
        
        normalized_error = (error - self.baseline_errors[symbol]) / self.error_stds[symbol]
        
        if normalized_error > self.anomaly_threshold:
            confidence = min(1.0, (normalized_error - self.anomaly_threshold) / 2 + 0.5)
            
            anomaly_type = self._determine_anomaly_type(features)
            
            event = AnomalyEvent(
                symbol=symbol,
                timestamp=time.time(),
                anomaly_type=anomaly_type,
                confidence=confidence,
                features=features,
                action=self._recommend_action(anomaly_type, features),
                expected_profit=self._estimate_profit(anomaly_type, features),
                duration_estimate=self._estimate_duration(anomaly_type, features)
            )
            
            self.event_queue.put(event)
            
            logger.info(f"Detected {anomaly_type} anomaly in {symbol} with confidence {confidence:.2f}")
    
    def _determine_anomaly_type(self, features: Dict[str, float]) -> str:
        """
        Determine the type of anomaly based on features
        
        Args:
            features: Extracted features
            
        Returns:
            str: Anomaly type
        """
        if features.get('volatility', 0) > 2.0:
            return "volatility_spike"
        elif features.get('volume_z', 0) > 3.0:
            return "volume_surge"
        elif features.get('price_momentum', 0) > 0.8:
            return "momentum_breakout"
        elif features.get('price_momentum', 0) < -0.8:
            return "momentum_breakdown"
        elif features.get('liquidity_imbalance', 0) > 0.7:
            return "liquidity_imbalance"
        else:
            return "pattern_anomaly"
    
    def _recommend_action(self, anomaly_type: str, features: Dict[str, float]) -> str:
        """
        Recommend trading action based on anomaly type
        
        Args:
            anomaly_type: Type of detected anomaly
            features: Extracted features
            
        Returns:
            str: Recommended action
        """
        if anomaly_type == "volatility_spike":
            return "HEDGE"
        elif anomaly_type == "volume_surge":
            return "MONITOR"
        elif anomaly_type == "momentum_breakout":
            return "BUY"
        elif anomaly_type == "momentum_breakdown":
            return "SELL"
        elif anomaly_type == "liquidity_imbalance":
            if features.get('bid_ask_imbalance', 0) > 0:
                return "BUY"
            else:
                return "SELL"
        else:
            return "MONITOR"
    
    def _estimate_profit(self, anomaly_type: str, features: Dict[str, float]) -> float:
        """
        Estimate potential profit from anomaly
        
        Args:
            anomaly_type: Type of detected anomaly
            features: Extracted features
            
        Returns:
            float: Estimated profit percentage
        """
        base_expectation = 0.0
        
        if anomaly_type == "momentum_breakout":
            base_expectation = 0.5
        elif anomaly_type == "momentum_breakdown":
            base_expectation = 0.5
        elif anomaly_type == "liquidity_imbalance":
            base_expectation = 0.3
        elif anomaly_type == "volatility_spike":
            base_expectation = 0.2
        elif anomaly_type == "volume_surge":
            base_expectation = 0.4
        
        volatility_factor = features.get('volatility', 1.0)
        momentum_factor = abs(features.get('price_momentum', 0.0))
        
        return base_expectation * (1 + 0.5 * momentum_factor) / volatility_factor
    
    def _estimate_duration(self, anomaly_type: str, features: Dict[str, float]) -> int:
        """
        Estimate duration of anomaly effect in seconds
        
        Args:
            anomaly_type: Type of detected anomaly
            features: Extracted features
            
        Returns:
            int: Estimated duration in seconds
        """
        if anomaly_type == "volatility_spike":
            return int(300 * features.get('volatility', 1.0))
        elif anomaly_type == "volume_surge":
            return int(600 * features.get('volume_z', 1.0) / 3.0)
        elif anomaly_type == "momentum_breakout" or anomaly_type == "momentum_breakdown":
            return int(1800 * abs(features.get('price_momentum', 0.0)))
        elif anomaly_type == "liquidity_imbalance":
            return int(120 * features.get('liquidity_imbalance', 1.0))
        else:
            return 300
    
    def _update_models_loop(self):
        """Background thread for periodically updating models"""
        while self.running:
            try:
                self._update_models()
                time.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error in model update loop: {e}")
                time.sleep(10)  # Wait before retrying
    
    def _update_models(self):
        """Update anomaly detection models for all symbols"""
        for symbol in self.symbols:
            if len(self.data_buffers[symbol]) < self.feature_window:
                continue
            
            features_list = []
            for i in range(len(self.data_buffers[symbol]) - self.feature_window + 1):
                window = self.data_buffers[symbol][i:i+self.feature_window]
                features = extract_features(window)
                if features is not None and len(features) > 0:
                    features_list.append(list(features.values()))
            
            if not features_list:
                continue
            
            features_tensor = torch.FloatTensor(features_list).to(self.device)
            
            input_dim = features_tensor.shape[1]
            if symbol not in self.models:
                self.models[symbol] = AnomalyDetector(input_dim).to(self.device)
            
            model = self.models[symbol]
            optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
            
            model.train()
            for epoch in range(5):  # Quick update with few epochs
                optimizer.zero_grad()
                reconstructed = model(features_tensor)
                loss = nn.MSELoss()(reconstructed, features_tensor)
                loss.backward()
                optimizer.step()
            
            model.eval()
            with torch.no_grad():
                errors = model.get_reconstruction_error(features_tensor)
                self.baseline_errors[symbol] = errors.mean().item()
                self.error_stds[symbol] = errors.std().item() + 1e-6  # Avoid division by zero
            
            logger.debug(f"Updated model for {symbol}, baseline error: {self.baseline_errors[symbol]:.6f}")
    
    def get_anomaly_events(self) -> List[AnomalyEvent]:
        """
        Get all pending anomaly events
        
        Returns:
            List[AnomalyEvent]: List of detected anomaly events
        """
        events = []
        while not self.event_queue.empty():
            try:
                events.append(self.event_queue.get_nowait())
            except queue.Empty:
                break
        return events
    
    def shutdown(self):
        """Shutdown the agent"""
        self.running = False
        if self.update_thread.is_alive():
            self.update_thread.join(timeout=1)
        logger.info("Anomaly Detection Agent shut down")


class AnomalyBasedStrategy(Strategy):
    """Trading strategy based on anomaly detection"""
    
    def __init__(
        self,
        symbols: List[str],
        min_confidence: float = 0.7,
        max_positions: int = 5
    ):
        """
        Initialize the anomaly-based trading strategy
        
        Args:
            symbols: List of trading symbols
            min_confidence: Minimum confidence for taking action
            max_positions: Maximum number of concurrent positions
        """
        super().__init__("AnomalyBasedStrategy")
        
        self.anomaly_agent = AnomalyDetectionAgent(symbols)
        self.min_confidence = min_confidence
        self.max_positions = max_positions
        self.active_positions = {}
        
        logger.info(f"Anomaly-based strategy initialized for {len(symbols)} symbols")
    
    def process_market_data(self, symbol: str, data: Dict[str, Any]):
        """
        Process new market data
        
        Args:
            symbol: Trading symbol
            data: Market data
        """
        self.anomaly_agent.add_data_point(symbol, data)
    
    def generate_signals(self) -> List[Dict[str, Any]]:
        """
        Generate trading signals based on detected anomalies
        
        Returns:
            List[Dict[str, Any]]: List of trading signals
        """
        signals = []
        
        events = self.anomaly_agent.get_anomaly_events()
        
        for event in events:
            if event.confidence < self.min_confidence:
                continue
            
            if len(self.active_positions) >= self.max_positions and event.symbol not in self.active_positions:
                continue
            
            if event.action in ["BUY", "SELL"]:
                signal = {
                    "symbol": event.symbol,
                    "action": event.action,
                    "confidence": event.confidence,
                    "reason": f"{event.anomaly_type} anomaly detected",
                    "expected_profit": event.expected_profit,
                    "timestamp": event.timestamp
                }
                
                signals.append(signal)
                
                if event.action == "BUY":
                    self.active_positions[event.symbol] = {
                        "entry_time": event.timestamp,
                        "expected_duration": event.duration_estimate
                    }
                elif event.action == "SELL" and event.symbol in self.active_positions:
                    self.active_positions.pop(event.symbol, None)
        
        current_time = time.time()
        for symbol, position in list(self.active_positions.items()):
            if current_time - position["entry_time"] > position["expected_duration"]:
                signals.append({
                    "symbol": symbol,
                    "action": "SELL",
                    "confidence": 0.8,
                    "reason": "Position duration exceeded",
                    "timestamp": current_time
                })
                self.active_positions.pop(symbol)
        
        return signals
    
    def shutdown(self):
        """Shutdown the strategy"""
        self.anomaly_agent.shutdown()
        logger.info("Anomaly-based strategy shut down")


def create_anomaly_detection_agent(symbols: List[str]) -> AnomalyDetectionAgent:
    """
    Create a new anomaly detection agent
    
    Args:
        symbols: List of trading symbols to monitor
        
    Returns:
        AnomalyDetectionAgent: New anomaly detection agent
    """
    return AnomalyDetectionAgent(symbols)
