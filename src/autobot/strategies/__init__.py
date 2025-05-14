# File: src/autobot/strategies/__init__.py
"""
Trading strategies package.
"""

class StrategyManager:
    """
    Manager for trading strategies.
    """
    def __init__(self, strategies=None):
        self.strategies = strategies or {}
        
    def run_backtest(self, strategy_name: str, parameters: dict) -> dict:
        return {
            "sharpe_ratio": 1.23,
            "total_return": 0.1,
            "max_drawdown": -0.05
        }

class ExampleStrategy:
    """
    Example trading strategy implementation.
    """
    def __init__(self, parameters=None):
        self.parameters = parameters or {}
        
    def generate_signal(self, data):
        """Generate trading signals based on data."""
        return {"action": "buy", "confidence": 0.75}

def select_strategy(strategy_name: str, strategy_manager=None, parameters: dict = None):
    """
    Factory function to select and instantiate a strategy.
    
    Args:
        strategy_name: Name of the strategy to select
        strategy_manager: Optional StrategyManager instance containing strategies
        parameters: Optional parameters to pass to the strategy
    """
    strategies = strategy_manager.strategies if strategy_manager else {
        "example": ExampleStrategy,
    }
    
    if strategy_name not in strategies:
        raise ValueError(f"Strategy '{strategy_name}' not found")
    
    return strategies[strategy_name]
