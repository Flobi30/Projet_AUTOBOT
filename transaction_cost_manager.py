"""
Transaction Cost and Slippage Manager for AUTOBOT
Phase 5 Implementation - Realistic Cost Modeling
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class TransactionCostManager:
    """
    Manages transaction costs and slippage for realistic backtesting.
    Adapted for 1-5 second trading intervals.
    """
    
    def __init__(self, fee_rate: float = 0.001, slippage_rate: float = 0.0005):
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        
    def apply_transaction_costs(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply transaction fees to strategy returns"""
        position_changes = df['signal'].diff().fillna(0)
        trade_signals = position_changes != 0
        
        df['fees'] = 0.0
        df.loc[trade_signals, 'fees'] = self.fee_rate
        
        df['strategy_returns'] = df['strategy_returns'] - df['fees']
        return df
    
    def apply_slippage(self, df: pd.DataFrame, volatility_col: str = 'volatility') -> pd.DataFrame:
        """Apply market slippage based on volatility"""
        position_changes = df['signal'].diff().fillna(0)
        trade_signals = position_changes != 0
        
        if volatility_col in df.columns:
            dynamic_slippage = self.slippage_rate * (1 + df[volatility_col])
        else:
            dynamic_slippage = self.slippage_rate
            
        df['slippage'] = 0.0
        df.loc[trade_signals, 'slippage'] = dynamic_slippage[trade_signals]
        df['strategy_returns'] = df['strategy_returns'] - df['slippage']
        
        return df
    
    def calculate_total_costs(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate total transaction costs for analysis"""
        total_fees = df['fees'].sum() if 'fees' in df.columns else 0.0
        total_slippage = df['slippage'].sum() if 'slippage' in df.columns else 0.0
        
        trade_count = (df['signal'].diff().fillna(0) != 0).sum()
        
        return {
            'total_fees': total_fees,
            'total_slippage': total_slippage,
            'total_costs': total_fees + total_slippage,
            'trade_count': trade_count,
            'avg_cost_per_trade': (total_fees + total_slippage) / max(trade_count, 1)
        }
    
    def optimize_execution_timing(self, market_data: Dict[str, Any]) -> float:
        """Optimize execution timing to minimize slippage"""
        volatility = market_data.get('volatility', 0.01)
        volume = market_data.get('volume', 1000000)
        spread = market_data.get('spread', 0.001)
        
        execution_score = 1.0 / (1 + volatility + spread - np.log(volume) * 0.1)
        return min(max(execution_score, 0.1), 1.0)
