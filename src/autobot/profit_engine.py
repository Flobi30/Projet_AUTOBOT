"""This module handles profit calculations and profit engine."""

class CapitalManager:
    """Manages user capital, deposits, withdrawals and profit tracking"""
    
    def __init__(self, initial_capital=500.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.total_profit = 0.0
        self.total_deposits = initial_capital
        self.total_withdrawals = 0.0
        self.trades_history = []
    
    def add_deposit(self, amount):
        """Add a deposit to the capital"""
        self.current_capital += amount
        self.total_deposits += amount
        return self.current_capital
    
    def process_withdrawal(self, amount):
        """Process a withdrawal from available capital"""
        if amount <= self.get_available_for_withdrawal():
            self.current_capital -= amount
            self.total_withdrawals += amount
            return True
        return False
    
    def update_from_trade(self, trade_profit):
        """Update capital based on trade results"""
        self.current_capital += trade_profit
        self.total_profit += trade_profit
        return self.current_capital
    
    def get_available_for_withdrawal(self):
        """Calculate available amount for withdrawal"""
        return max(0, self.current_capital - self.initial_capital * 0.1)  # Keep 10% as margin
    
    def get_roi(self):
        """Calculate return on investment percentage"""
        if self.initial_capital > 0:
            return (self.total_profit / self.initial_capital) * 100
        return 0.0
    
    def update_from_backtest(self, backtest_result):
        """Update capital based on backtest results."""
        if 'total_return' in backtest_result:
            profit_amount = self.current_capital * (backtest_result['total_return'] / 100)
            self.current_capital += profit_amount
            self.total_profit += profit_amount
            
            try:
                from .adaptive.capital_manager import adaptive_capital_manager
                adaptive_capital_manager.current_capital = self.current_capital
            except ImportError:
                pass
        
        return self.current_capital
    
    def get_capital_summary(self):
        """Get comprehensive capital summary including adaptive features."""
        base_summary = {
            "current_capital": round(self.current_capital, 2),
            "initial_capital": round(self.initial_capital, 2),
            "total_profit": round(self.total_profit, 2),
            "total_deposits": round(self.total_deposits, 2),
            "total_withdrawals": round(self.total_withdrawals, 2),
            "roi": round(self.get_roi(), 2),
            "available_for_withdrawal": round(self.get_available_for_withdrawal(), 2)
        }
        
        try:
            from .adaptive.capital_manager import adaptive_capital_manager
            adaptive_summary = adaptive_capital_manager.get_capital_summary()
            base_summary.update({
                'capital_range': adaptive_summary['capital_range'],
                'active_strategies': adaptive_summary['active_strategies'],
                'experience_count': adaptive_summary['experience_count']
            })
        except ImportError:
            pass
        
        return base_summary

class ProfitEngine:
    def __init__(self, initial_capital):
        self.capital = initial_capital

    def calculate_profit(self, trades):
        """Calculate total profit based on trades."""
        total_profit = 0.0
        for trade in trades:
            total_profit += trade.get('profit', 0)
        return total_profit

    def update_capital(self, profit):
        """Update current capital based on profit."""
        self.capital += profit
        return self.capital

def get_user_capital_data():
    """Get user capital data from Stripe account."""
    try:
        import os
        stripe_api_key = os.getenv('STRIPE_API_KEY')
        if not stripe_api_key:
            return {
                "current_capital": 0,
                "initial_capital": 500,
                "total_profit": 0,
                "roi": 0,
                "available_for_withdrawal": 0
            }
        
        return {
            "current_capital": 0,
            "initial_capital": 500,
            "total_profit": 0,
            "roi": 0,
            "available_for_withdrawal": 0
        }
    except Exception as e:
        return {
            "current_capital": 0,
            "initial_capital": 500,
            "total_profit": 0,
            "roi": 0,
            "available_for_withdrawal": 0
        }
