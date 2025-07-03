"""
Advanced Risk Management for AUTOBOT
Phase 3 Implementation - Dynamic Stop-Loss and Position Sizing
"""

import logging
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)

class AdvancedRiskManager:
    """
    Advanced risk management with dynamic stop-loss and adaptive position sizing.
    Calibrated for 1-5 second trading intervals and AMD hardware optimization.
    """
    
    def __init__(self, stop_loss_pct: float = 0.02, take_profit_pct: float = 0.06, 
                 max_risk_per_trade: float = 0.01, max_portfolio_risk: float = 0.05):
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_risk_per_trade = max_risk_per_trade
        self.max_portfolio_risk = max_portfolio_risk
        
    def apply_dynamic_stop_loss(self, df: pd.DataFrame, entry_price: float, volatility: float):
        """Apply dynamic stop-loss based on volatility"""
        dynamic_stop_pct = max(self.stop_loss_pct, volatility * 1.5)
        df['stop_loss'] = entry_price * (1 - dynamic_stop_pct)
        df['take_profit'] = entry_price * (1 + self.take_profit_pct)
        
        df.loc[df['close'] <= df['stop_loss'], 'signal'] = 0
        df.loc[df['close'] >= df['take_profit'], 'signal'] = 0
        return df
    
    def calculate_position_size(self, capital: float, volatility: float, 
                              current_portfolio_risk: float = 0.0) -> float:
        """Calculate adaptive position size based on volatility and portfolio risk"""
        if current_portfolio_risk >= self.max_portfolio_risk:
            return 0.0
            
        max_risk = capital * self.max_risk_per_trade
        volatility_adjusted_risk = max_risk / max(volatility, 0.01)
        
        position_size = min(volatility_adjusted_risk, capital * 0.1)
        
        risk_factor = 1 - (current_portfolio_risk / self.max_portfolio_risk)
        return position_size * risk_factor
    
    def calculate_portfolio_risk(self, positions: List[Dict[str, Any]]) -> float:
        """Calculate current portfolio risk level"""
        total_risk = 0.0
        for position in positions:
            position_risk = position.get('amount', 0) * position.get('volatility', 0.01)
            total_risk += position_risk
        return total_risk
    
    def should_reduce_exposure(self, current_risk: float, market_volatility: float) -> bool:
        """Determine if exposure should be reduced based on risk metrics"""
        risk_threshold = self.max_portfolio_risk * 0.8
        volatility_threshold = 0.05
        
        return current_risk > risk_threshold or market_volatility > volatility_threshold
    
    def get_risk_metrics(self, positions: List[Dict[str, Any]]) -> Dict[str, float]:
        """Get comprehensive risk metrics for monitoring"""
        portfolio_risk = self.calculate_portfolio_risk(positions)
        
        return {
            'portfolio_risk': portfolio_risk,
            'risk_utilization': portfolio_risk / self.max_portfolio_risk,
            'max_risk_per_trade': self.max_risk_per_trade,
            'stop_loss_pct': self.stop_loss_pct,
            'take_profit_pct': self.take_profit_pct,
            'position_count': len(positions)
        }
