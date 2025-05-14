import logging
import numpy as np
from typing import Dict, Any, Optional, List, Tuple, Union
from datetime import datetime, timedelta

from autobot.trading.position import Position
from autobot.trading.order import Order, OrderSide

logger = logging.getLogger(__name__)

class RiskManager:
    """
    Enhanced risk manager for AUTOBOT trading system.
    Handles position sizing, risk allocation, drawdown protection,
    and portfolio management.
    """
    
    def __init__(
        self,
        initial_capital: float,
        max_risk_per_trade_pct: float = 2.0,
        max_portfolio_risk_pct: float = 5.0,
        max_drawdown_pct: float = 20.0,
        position_sizing_method: str = "risk_based",
        correlation_threshold: float = 0.7,
        volatility_lookback: int = 20,
        risk_free_rate: float = 0.0
    ):
        """
        Initialize the risk manager.
        
        Args:
            initial_capital: Starting capital amount
            max_risk_per_trade_pct: Maximum risk percentage per trade (0-100)
            max_portfolio_risk_pct: Maximum portfolio risk percentage (0-100)
            max_drawdown_pct: Maximum allowed drawdown percentage (0-100)
            position_sizing_method: Method for position sizing ('risk_based', 'kelly', 'fixed', 'percent_equity')
            correlation_threshold: Threshold for considering assets correlated
            volatility_lookback: Number of periods to look back for volatility calculation
            risk_free_rate: Annual risk-free rate for Sharpe ratio calculation
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.max_risk_per_trade_pct = max_risk_per_trade_pct / 100.0
        self.max_portfolio_risk_pct = max_portfolio_risk_pct / 100.0
        self.max_drawdown_pct = max_drawdown_pct / 100.0
        self.position_sizing_method = position_sizing_method
        self.correlation_threshold = correlation_threshold
        self.volatility_lookback = volatility_lookback
        self.risk_free_rate = risk_free_rate
        
        self.peak_capital = initial_capital
        self.current_drawdown_pct = 0.0
        self.positions: List[Position] = []
        self.historical_equity: List[Tuple[datetime, float]] = [(datetime.now(), initial_capital)]
        self.trade_history: List[Dict[str, Any]] = []
        
        logger.info(f"Risk Manager initialized with {initial_capital} capital and {max_risk_per_trade_pct}% max risk per trade")
    
    def calculate_position_size(
        self, 
        symbol: str,
        entry_price: float,
        stop_loss: float,
        side: OrderSide,
        win_rate: Optional[float] = None,
        reward_risk_ratio: Optional[float] = None
    ) -> float:
        """
        Calculate the position size based on risk parameters and position sizing method.
        
        Args:
            symbol: Trading pair symbol
            entry_price: Entry price for the position
            stop_loss: Stop loss price for the position
            side: Order side (buy/sell)
            win_rate: Historical win rate for this strategy (for Kelly criterion)
            reward_risk_ratio: Average reward to risk ratio (for Kelly criterion)
            
        Returns:
            float: Position size in base currency units
        """
        risk_amount = self.current_capital * self.max_risk_per_trade_pct
        
        if side == OrderSide.BUY:
            stop_distance_pct = (entry_price - stop_loss) / entry_price
        else:
            stop_distance_pct = (stop_loss - entry_price) / entry_price
        
        stop_distance_pct = abs(stop_distance_pct)
        
        if self.position_sizing_method == "risk_based":
            position_size = risk_amount / (entry_price * stop_distance_pct)
            
        elif self.position_sizing_method == "kelly":
            if win_rate is None or reward_risk_ratio is None:
                logger.warning("Win rate or reward/risk ratio not provided for Kelly sizing, using risk-based instead")
                position_size = risk_amount / (entry_price * stop_distance_pct)
            else:
                kelly_fraction = (win_rate * reward_risk_ratio - (1 - win_rate)) / reward_risk_ratio
                kelly_fraction = max(0, kelly_fraction * 0.5)
                position_size = (self.current_capital * kelly_fraction) / entry_price
                
        elif self.position_sizing_method == "fixed":
            position_size = risk_amount / entry_price
            
        elif self.position_sizing_method == "percent_equity":
            position_size = (self.current_capital * self.max_risk_per_trade_pct) / entry_price
            
        else:
            position_size = risk_amount / (entry_price * stop_distance_pct)
        
        portfolio_risk = self.calculate_portfolio_risk()
        new_position_risk = risk_amount / self.current_capital
        
        if portfolio_risk + new_position_risk > self.max_portfolio_risk_pct:
            logger.warning(f"Position size reduced due to portfolio risk limit ({portfolio_risk:.2%} + {new_position_risk:.2%} > {self.max_portfolio_risk_pct:.2%})")
            available_risk = self.max_portfolio_risk_pct - portfolio_risk
            if available_risk <= 0:
                logger.warning("No risk budget available, position size set to 0")
                return 0
            
            position_size *= (available_risk / new_position_risk)
        
        logger.info(f"Calculated position size for {symbol}: {position_size} units (risk: {risk_amount})")
        return position_size
    
    def calculate_portfolio_risk(self) -> float:
        """
        Calculate the current portfolio risk as a percentage of capital.
        
        Returns:
            float: Portfolio risk as a decimal percentage
        """
        if not self.positions:
            return 0.0
        
        total_risk = 0.0
        
        for position in self.positions:
            if not position.is_open:
                continue
                
            if position.side == OrderSide.BUY:
                risk_per_unit = position.entry_price - (position.stop_loss or 0)
            else:
                risk_per_unit = (position.stop_loss or 0) - position.entry_price
            
            risk_per_unit = abs(risk_per_unit)
            
            position_risk = risk_per_unit * position.amount
            
            total_risk += position_risk / self.current_capital
        
        return total_risk
    
    def check_correlation(self, symbol: str, price_history: Dict[str, List[float]]) -> List[str]:
        """
        Check for correlation with existing positions to avoid overexposure.
        
        Args:
            symbol: Symbol to check
            price_history: Dictionary of price histories for all relevant symbols
            
        Returns:
            List: List of correlated symbols
        """
        if symbol not in price_history or not self.positions:
            return []
        
        correlated_symbols = []
        
        for position in self.positions:
            if not position.is_open or position.symbol == symbol:
                continue
                
            if position.symbol not in price_history:
                continue
                
            try:
                symbol_prices = np.array(price_history[symbol])
                position_prices = np.array(price_history[position.symbol])
                
                min_length = min(len(symbol_prices), len(position_prices))
                if min_length < 10:  # Need at least 10 data points
                    continue
                    
                symbol_prices = symbol_prices[-min_length:]
                position_prices = position_prices[-min_length:]
                
                correlation = np.corrcoef(symbol_prices, position_prices)[0, 1]
                
                if abs(correlation) >= self.correlation_threshold:
                    correlated_symbols.append(position.symbol)
                    logger.info(f"High correlation ({correlation:.2f}) detected between {symbol} and {position.symbol}")
            except Exception as e:
                logger.error(f"Error calculating correlation: {str(e)}")
        
        return correlated_symbols
    
    def update_capital(self, new_capital: float):
        """
        Update the current capital amount and check for drawdown.
        
        Args:
            new_capital: New capital amount
        """
        self.current_capital = new_capital
        self.historical_equity.append((datetime.now(), new_capital))
        
        if new_capital > self.peak_capital:
            self.peak_capital = new_capital
        
        self.current_drawdown_pct = (self.peak_capital - new_capital) / self.peak_capital
        
        if self.current_drawdown_pct >= self.max_drawdown_pct:
            logger.warning(f"Maximum drawdown exceeded: {self.current_drawdown_pct:.2%} > {self.max_drawdown_pct:.2%}")
    
    def add_position(self, position: Position):
        """
        Add a position to the risk manager.
        
        Args:
            position: Position object
        """
        self.positions.append(position)
        logger.info(f"Added position {position.id} for {position.symbol} to risk manager")
    
    def close_position(self, position_id: str, exit_price: float):
        """
        Close a position and update capital.
        
        Args:
            position_id: ID of the position to close
            exit_price: Exit price for the position
        """
        for position in self.positions:
            if position.id == position_id and position.is_open:
                position.close(exit_price)
                
                self.trade_history.append({
                    "position_id": position.id,
                    "symbol": position.symbol,
                    "side": position.side.value,
                    "entry_price": position.entry_price,
                    "exit_price": position.exit_price,
                    "amount": position.amount,
                    "realized_pnl": position.realized_pnl,
                    "entry_time": position.created_at,
                    "exit_time": position.exit_time
                })
                
                self.update_capital(self.current_capital + position.realized_pnl)
                
                logger.info(f"Closed position {position_id} at {exit_price} with P&L: {position.realized_pnl}")
                return
        
        logger.warning(f"Position {position_id} not found or already closed")
    
    def calculate_portfolio_metrics(self) -> Dict[str, Any]:
        """
        Calculate portfolio performance metrics.
        
        Returns:
            Dict: Dictionary of portfolio metrics
        """
        if len(self.historical_equity) < 2:
            return {
                "total_return_pct": 0.0,
                "annualized_return_pct": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0
            }
        
        equity_values = [equity for _, equity in self.historical_equity]
        returns = np.diff(equity_values) / equity_values[:-1]
        
        total_return_pct = (self.current_capital / self.initial_capital) - 1
        
        first_date = self.historical_equity[0][0]
        last_date = self.historical_equity[-1][0]
        days = (last_date - first_date).days
        if days < 1:
            days = 1
        annualized_return_pct = ((1 + total_return_pct) ** (365 / days)) - 1
        
        if len(returns) > 1:
            daily_returns_mean = np.mean(returns)
            daily_returns_std = np.std(returns)
            daily_risk_free_rate = (1 + self.risk_free_rate) ** (1/365) - 1
            sharpe_ratio = (daily_returns_mean - daily_risk_free_rate) / daily_returns_std if daily_returns_std > 0 else 0
            sharpe_ratio *= np.sqrt(252)  # Annualize
        else:
            sharpe_ratio = 0.0
        
        peak = equity_values[0]
        max_drawdown = 0.0
        
        for equity in equity_values:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak
            max_drawdown = max(max_drawdown, drawdown)
        
        if self.trade_history:
            winning_trades = [trade for trade in self.trade_history if trade["realized_pnl"] > 0]
            losing_trades = [trade for trade in self.trade_history if trade["realized_pnl"] <= 0]
            
            win_rate = len(winning_trades) / len(self.trade_history) if self.trade_history else 0
            
            gross_profit = sum(trade["realized_pnl"] for trade in winning_trades)
            gross_loss = abs(sum(trade["realized_pnl"] for trade in losing_trades))
            
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        else:
            win_rate = 0.0
            profit_factor = 0.0
        
        return {
            "total_return_pct": total_return_pct * 100,
            "annualized_return_pct": annualized_return_pct * 100,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown_pct": max_drawdown * 100,
            "win_rate": win_rate * 100,
            "profit_factor": profit_factor,
            "current_capital": self.current_capital,
            "current_drawdown_pct": self.current_drawdown_pct * 100,
            "open_positions": len([p for p in self.positions if p.is_open]),
            "total_trades": len(self.trade_history)
        }
    
    def should_stop_trading(self) -> Tuple[bool, str]:
        """
        Check if trading should be stopped based on risk parameters.
        
        Returns:
            Tuple: (should_stop, reason)
        """
        if self.current_drawdown_pct >= self.max_drawdown_pct:
            return True, f"Maximum drawdown exceeded: {self.current_drawdown_pct:.2%} > {self.max_drawdown_pct:.2%}"
        
        if self.current_capital < self.initial_capital * 0.5:
            return True, f"Capital reduced by more than 50%: {self.current_capital} < {self.initial_capital * 0.5}"
        
        if len(self.trade_history) >= 10:
            recent_trades = self.trade_history[-10:]
            losing_trades = [trade for trade in recent_trades if trade["realized_pnl"] <= 0]
            
            if len(losing_trades) >= 8:
                return True, f"Too many recent losing trades: {len(losing_trades)}/10"
        
        return False, ""

def calculate_position_size(balance: float, risk_pct: float, stop_loss: float) -> float:
    """
    Calculate position size based on account balance and risk percentage.
    
    Args:
        balance: Account balance
        risk_pct: Risk percentage (0-100)
        stop_loss: Stop loss amount
        
    Returns:
        float: Position size
    """
    risk_amount = balance * (risk_pct / 100)
    size = risk_amount / stop_loss
    return size
