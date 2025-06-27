import json
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

from ..rl.meta_learning import MetaLearner, create_meta_learner
from ..agents.profit_optimizer import ProfitOptimizer
from ..rl.accelerated_learning import ExperienceBuffer
from ..profit_engine import CapitalManager
from ..db.models import SessionLocal, CapitalHistory, BacktestResult, create_tables

logger = logging.getLogger(__name__)

class AdaptiveCapitalManager:
    """
    Adaptive capital management system that learns and optimizes strategies
    based on available capital amounts.
    """
    
    def __init__(self, initial_capital: float = 500.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        
        self.meta_learner = create_meta_learner(
            strategy_pool_size=10,
            auto_adapt=True,
            visible_interface=True
        )
        self.profit_optimizer = ProfitOptimizer(initial_capital=initial_capital)
        self.experience_buffer = ExperienceBuffer(max_size=1000)
        self.capital_manager = CapitalManager(initial_capital=initial_capital)
        
        self.capital_performance_history = {}
        self.strategy_capital_mapping = {}
        
        create_tables()
        
        self._load_historical_performance()
    
    def get_capital_range(self, capital: float) -> str:
        """Categorize capital into ranges for adaptive learning."""
        if capital < 750:
            return "low_capital"
        elif capital < 2500:
            return "medium_capital"
        elif capital < 7500:
            return "high_capital"
        else:
            return "ultra_capital"
    
    def adapt_strategy_parameters(self, strategy_params: Dict, capital: float) -> Dict:
        """
        Adapt strategy parameters based on available capital.
        
        Higher capital allows for:
        - More aggressive position sizing
        - Longer holding periods
        - More sophisticated strategies
        """
        capital_range = self.get_capital_range(capital)
        adapted_params = strategy_params.copy()
        
        capital_multiplier = capital / self.initial_capital
        
        if 'position_size' in adapted_params:
            adapted_params['position_size'] *= min(capital_multiplier, 5.0)
        
        if 'stop_loss' in adapted_params:
            adapted_params['stop_loss'] *= max(0.5, 1.0 / np.sqrt(capital_multiplier))
        
        if 'lookback_period' in adapted_params:
            adapted_params['lookback_period'] = int(
                adapted_params['lookback_period'] * min(capital_multiplier * 0.5 + 0.5, 2.0)
            )
        
        strategy_id = f"{strategy_params.get('name', 'unknown')}_{capital_range}"
        if strategy_id not in self.strategy_capital_mapping:
            self.strategy_capital_mapping[strategy_id] = {}
        self.strategy_capital_mapping[strategy_id][capital_range] = adapted_params
        
        return adapted_params
    
    def update_performance(self, strategy_name: str, capital: float, 
                          returns: float, sharpe: float = None, 
                          drawdown: float = None, win_rate: float = None):
        """Update performance metrics for capital-aware learning."""
        capital_range = self.get_capital_range(capital)
        
        if capital_range not in self.capital_performance_history:
            self.capital_performance_history[capital_range] = []
        
        performance_record = {
            'timestamp': datetime.utcnow(),
            'strategy': strategy_name,
            'capital': capital,
            'returns': returns,
            'sharpe': sharpe,
            'drawdown': drawdown,
            'win_rate': win_rate
        }
        
        self.capital_performance_history[capital_range].append(performance_record)
        
        strategy_id = f"{strategy_name}_{capital_range}"
        self.meta_learner.update_performance(strategy_id, returns, sharpe, drawdown, win_rate)
        
        experience = {
            'state': {'capital': capital, 'capital_range': capital_range},
            'action': {'strategy': strategy_name},
            'reward': returns,
            'next_state': {'capital': capital * (1 + returns / 100)}
        }
        self.experience_buffer.add_experience(experience)
        
        self._save_performance_to_db(strategy_name, capital, returns, sharpe, drawdown)
    
    def get_best_strategy_for_capital(self, capital: float) -> Tuple[str, Dict]:
        """Get the best strategy adapted for the current capital level."""
        capital_range = self.get_capital_range(capital)
        
        capital_strategies = {
            k: v for k, v in self.meta_learner.get_all_strategies().items()
            if capital_range in k
        }
        
        if not capital_strategies:
            best_strategy = self.meta_learner.get_best_strategy()
            if best_strategy:
                strategy_id, strategy_info = best_strategy
                return strategy_info['name'], self.adapt_strategy_parameters(
                    strategy_info['params'], capital
                )
        else:
            best_strategy_id = max(capital_strategies.keys(), 
                                 key=lambda x: capital_strategies[x]['weight'])
            strategy_info = capital_strategies[best_strategy_id]
            return strategy_info['name'], strategy_info['params']
        
        return "moving_average_crossover", {"fast_period": 10, "slow_period": 20}
    
    def _load_historical_performance(self):
        """Load historical performance data from database."""
        try:
            db = SessionLocal()
            results = db.query(BacktestResult).all()
            
            for result in results:
                capital_range = self.get_capital_range(result.initial_capital)
                if capital_range not in self.capital_performance_history:
                    self.capital_performance_history[capital_range] = []
                
                self.capital_performance_history[capital_range].append({
                    'timestamp': result.timestamp,
                    'strategy': result.strategy,
                    'capital': result.initial_capital,
                    'returns': result.total_return,
                    'sharpe': result.sharpe_ratio,
                    'drawdown': result.max_drawdown
                })
            
            db.close()
            logger.info(f"Loaded {len(results)} historical performance records")
        except Exception as e:
            logger.warning(f"Could not load historical performance: {e}")
    
    def _save_performance_to_db(self, strategy_name: str, capital: float, 
                              returns: float, sharpe: float = None, 
                              drawdown: float = None):
        """Save performance data to database for persistence."""
        try:
            db = SessionLocal()
            
            result = BacktestResult(
                id=f"{strategy_name}_{int(datetime.utcnow().timestamp())}",
                symbol="ADAPTIVE",
                strategy=strategy_name,
                initial_capital=capital,
                final_capital=capital * (1 + returns / 100),
                total_return=returns,
                sharpe_ratio=sharpe or 0.0,
                max_drawdown=drawdown or 0.0,
                strategy_params=json.dumps(self.strategy_capital_mapping.get(
                    f"{strategy_name}_{self.get_capital_range(capital)}", {}
                ))
            )
            
            db.add(result)
            db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Could not save performance to database: {e}")
    
    def get_capital_summary(self) -> Dict:
        """Get comprehensive capital and performance summary."""
        return {
            'current_capital': self.current_capital,
            'initial_capital': self.initial_capital,
            'capital_range': self.get_capital_range(self.current_capital),
            'total_return': ((self.current_capital - self.initial_capital) / self.initial_capital) * 100,
            'performance_history': self.capital_performance_history,
            'active_strategies': len(self.meta_learner.get_all_strategies()),
            'experience_count': len(self.experience_buffer.experiences)
        }
