import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple, List, Optional
from enum import Enum

class TradingAction(Enum):
    HOLD = 0
    BUY = 1
    SELL = 2

class TradingEnv:
    """
    Trading environment for reinforcement learning.
    """
    def __init__(
        self,
        data: pd.DataFrame,
        initial_balance: float = 10000.0,
        transaction_fee: float = 0.001,
        window_size: int = 10,
        reward_scaling: float = 0.01
    ):
        """
        Initialize the trading environment.
        
        Args:
            data: DataFrame with OHLCV data
            initial_balance: Initial account balance
            transaction_fee: Fee per transaction as a fraction
            window_size: Number of past observations to include in state
            reward_scaling: Scaling factor for rewards
        """
        self.data = data
        self.initial_balance = initial_balance
        self.transaction_fee = transaction_fee
        self.window_size = window_size
        self.reward_scaling = reward_scaling
        
        self.action_space = len(TradingAction)
        self.observation_space = window_size * 5 + 2  # OHLCV * window_size + position + balance
        
        self.reset()
    
    def reset(self):
        """
        Reset the environment to initial state.
        
        Returns:
            np.ndarray: Initial state observation
        """
        self.current_step = self.window_size
        self.balance = self.initial_balance
        self.shares_held = 0
        self.current_price = 0
        self.cost_basis = 0
        self.total_trades = 0
        self.total_profit = 0
        self.history = []
        
        return self._get_observation()
    
    def step(self, action):
        """
        Take a step in the environment.
        
        Args:
            action: Action to take (0: HOLD, 1: BUY, 2: SELL)
            
        Returns:
            Tuple containing:
                - Next state observation
                - Reward
                - Done flag
                - Info dictionary
        """
        action = TradingAction(action) if isinstance(action, int) else action
        
        self.current_price = self.data.iloc[self.current_step]['close']
        
        reward = 0
        done = False
        info = {}
        
        if action == TradingAction.BUY and self.balance > 0:
            max_shares = self.balance / (self.current_price * (1 + self.transaction_fee))
            shares_bought = max_shares
            cost = shares_bought * self.current_price * (1 + self.transaction_fee)
            
            self.balance -= cost
            self.shares_held += shares_bought
            self.cost_basis = self.current_price
            self.total_trades += 1
            
            info['action'] = 'buy'
            info['shares_bought'] = shares_bought
            info['cost'] = cost
            
        elif action == TradingAction.SELL and self.shares_held > 0:
            shares_sold = self.shares_held
            sale_value = shares_sold * self.current_price * (1 - self.transaction_fee)
            
            self.balance += sale_value
            profit = sale_value - (shares_sold * self.cost_basis)
            self.total_profit += profit
            self.shares_held = 0
            self.cost_basis = 0
            self.total_trades += 1
            
            reward = profit * self.reward_scaling
            
            info['action'] = 'sell'
            info['shares_sold'] = shares_sold
            info['sale_value'] = sale_value
            info['profit'] = profit
            
        else:
            info['action'] = 'hold'
            
            reward = -0.001
        
        portfolio_value = self.balance + (self.shares_held * self.current_price)
        
        self.history.append({
            'step': self.current_step,
            'price': self.current_price,
            'action': action.name,
            'shares_held': self.shares_held,
            'balance': self.balance,
            'portfolio_value': portfolio_value,
            'reward': reward
        })
        
        self.current_step += 1
        
        if self.current_step >= len(self.data) - 1:
            done = True
            
            info['final_portfolio_value'] = portfolio_value
            info['initial_portfolio_value'] = self.initial_balance
            info['total_profit'] = portfolio_value - self.initial_balance
            info['total_trades'] = self.total_trades
            
            final_reward = (portfolio_value - self.initial_balance) * self.reward_scaling
            reward += final_reward
        
        next_observation = self._get_observation()
        
        return next_observation, reward, done, info
    
    def _get_observation(self):
        """
        Get the current state observation.
        
        Returns:
            np.ndarray: State observation
        """
        frame = self.data.iloc[self.current_step - self.window_size:self.current_step]
        
        normalized_frame = self._normalize_frame(frame)
        
        flattened_frame = normalized_frame.values.flatten()
        
        position = np.array([
            self.shares_held > 0,  # Position indicator (0: no position, 1: long position)
            self.balance / self.initial_balance  # Normalized balance
        ])
        
        observation = np.concatenate([flattened_frame, position])
        
        return observation
    
    def _normalize_frame(self, frame):
        """
        Normalize the OHLCV data.
        
        Args:
            frame: DataFrame with OHLCV data
            
        Returns:
            pd.DataFrame: Normalized data
        """
        normalized = frame.copy()
        
        for column in ['open', 'high', 'low', 'close']:
            normalized[column] = normalized[column] / normalized['close'].iloc[-1] - 1
        
        if 'volume' in normalized.columns:
            max_volume = normalized['volume'].max()
            if max_volume > 0:
                normalized['volume'] = normalized['volume'] / max_volume
        
        return normalized
    
    def render(self, mode='human'):
        """
        Render the environment.
        
        Args:
            mode: Rendering mode ('human' or 'rgb_array')
            
        Returns:
            Optional[np.ndarray]: Rendered image if mode is 'rgb_array'
        """
        if len(self.history) == 0:
            return None
            
        last_step = self.history[-1]
        print(f"Step: {last_step['step']}")
        print(f"Price: {last_step['price']:.2f}")
        print(f"Action: {last_step['action']}")
        print(f"Shares held: {last_step['shares_held']:.6f}")
        print(f"Balance: {last_step['balance']:.2f}")
        print(f"Portfolio value: {last_step['portfolio_value']:.2f}")
        print(f"Reward: {last_step['reward']:.6f}")
        print("-" * 50)
        
        return None
    
    def get_history_dataframe(self):
        """
        Get the history as a DataFrame.
        
        Returns:
            pd.DataFrame: History of steps, actions, and results
        """
        return pd.DataFrame(self.history)
