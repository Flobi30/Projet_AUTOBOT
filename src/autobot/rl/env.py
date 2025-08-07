import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces
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
        initial_balance: float = 500.0,
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
        self.portfolio_history = [self.initial_balance]
        
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
        
        self.portfolio_value = self.balance + (self.shares_held * self.current_price)
        self.portfolio_history.append(self.portfolio_value)
        
        self.history.append({
            'step': self.current_step,
            'price': self.current_price,
            'action': action.name,
            'shares_held': self.shares_held,
            'balance': self.balance,
            'portfolio_value': self.portfolio_value,
            'reward': reward
        })
        
        self.current_step += 1
        
        if self.current_step >= len(self.data) - 1:
            done = True
            
            info['final_portfolio_value'] = self.portfolio_value
            info['initial_portfolio_value'] = self.initial_balance
            info['total_profit'] = self.portfolio_value - self.initial_balance
            info['total_trades'] = self.total_trades
            
            final_reward = (self.portfolio_value - self.initial_balance) * self.reward_scaling
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

class TradingEnvironment(gym.Env):
    """
    Gymnasium-compatible trading environment for reinforcement learning.
    """
    metadata = {'render.modes': ['human']}
    
    def __init__(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_balance: float = 500.0,
        transaction_fee: float = 0.001,
        window_size: int = 10,
        reward_scaling: float = 0.01,
        data: Optional[pd.DataFrame] = None
    ):
        """
        Initialize the trading environment.
        
        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe for data
            start_date: Start date for data
            end_date: End date for data
            initial_balance: Initial account balance
            transaction_fee: Fee per transaction as a fraction
            window_size: Number of past observations to include in state
            reward_scaling: Scaling factor for rewards
            data: Optional DataFrame with OHLCV data (if not provided, will be fetched)
        """
        super(TradingEnvironment, self).__init__()
        
        self.symbol = symbol
        self.timeframe = timeframe
        self.start_date = start_date
        self.end_date = end_date
        self.initial_balance = initial_balance
        self.transaction_fee = transaction_fee
        self.window_size = window_size
        self.reward_scaling = reward_scaling
        
        if data is not None:
            self.data = data
        else:
            self.data = self._fetch_data()
        
        self.action_space = spaces.Discrete(3)  # HOLD, BUY, SELL
        
        # Observation space: OHLCV * window_size + position + balance
        obs_dim = window_size * 5 + 2
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32
        )
        
        # Initialize state
        self.reset()
    
    def _fetch_data(self) -> pd.DataFrame:
        """
        Fetch OHLCV data for the specified symbol and timeframe.
        
        Returns:
            pd.DataFrame: OHLCV data
        """
        try:
            from autobot.data.real_providers import get_market_data
            
            real_data = get_historical_data(
                symbol=self.symbol,
                timeframe=self.timeframe,
                start_date=self.start_date,
                end_date=self.end_date
            )
            
            if real_data is not None and len(real_data) > 0:
                return real_data
                
        except Exception as e:
            print(f"Error fetching real data: {e}")
        
        n_points = 1000
        dates = pd.date_range(
            start=self.start_date or '2020-01-01',
            end=self.end_date or '2022-01-01',
            periods=n_points
        )
        
        base_price = 100.0
        data = pd.DataFrame({
            'timestamp': dates,
            'open': [base_price] * n_points,
            'high': [base_price * 1.01] * n_points,
            'low': [base_price * 0.99] * n_points,
            'close': [base_price] * n_points,
            'volume': [1000.0] * n_points
        })
        
        return data
    
    def reset(self, seed=None, options=None):
        """
        Reset the environment to initial state.
        
        Returns:
            np.ndarray: Initial state observation
            dict: Empty info dictionary
        """
        super().reset(seed=seed)
        
        self.current_step = self.window_size
        self.balance = self.initial_balance
        self.shares_held = 0
        self.current_price = 0
        self.cost_basis = 0
        self.total_trades = 0
        self.total_profit = 0
        self.history = []
        self.portfolio_value = self.initial_balance
        self.portfolio_history = [self.initial_balance]
        
        observation = self._get_observation()
        info = {}
        
        return observation, info
    
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
                - Truncated flag
                - Info dictionary
        """
        self.current_price = self.data.iloc[self.current_step]['close']
        
        reward = 0
        done = False
        truncated = False
        info = {}
        
        if action == 1:  # BUY
            if self.balance > 0:
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
            else:
                info['action'] = 'buy_failed'
                reward = -0.001
                
        elif action == 2:  # SELL
            if self.shares_held > 0:
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
                info['action'] = 'sell_failed'
                reward = -0.001
                
        else:  # HOLD
            info['action'] = 'hold'
            reward = -0.0001  # Small negative reward to encourage action
        
        self.portfolio_value = self.balance + (self.shares_held * self.current_price)
        self.portfolio_history.append(self.portfolio_value)
        
        self.history.append({
            'step': self.current_step,
            'price': self.current_price,
            'action': info['action'],
            'shares_held': self.shares_held,
            'balance': self.balance,
            'portfolio_value': self.portfolio_value,
            'reward': reward
        })
        
        self.current_step += 1
        
        if self.current_step >= len(self.data) - 1:
            done = True
            
            info['final_portfolio_value'] = self.portfolio_value
            info['initial_portfolio_value'] = self.initial_balance
            info['total_profit'] = self.portfolio_value - self.initial_balance
            info['total_trades'] = self.total_trades
            
            final_reward = (self.portfolio_value - self.initial_balance) * self.reward_scaling
            reward += final_reward
        
        next_observation = self._get_observation()
        
        return next_observation, reward, done, truncated, info
    
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
            float(self.shares_held > 0),  # Position indicator (0: no position, 1: long position)
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
