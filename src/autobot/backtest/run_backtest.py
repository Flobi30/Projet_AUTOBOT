
def run_backtest(df, strategy_fn, initial_capital):
    """Run a backtest with the given data, strategy, and initial capital."""
    capital = initial_capital
    positions = []  # Track positions
    portfolio_value = []  # Track portfolio value over time
    for index, row in df.iterrows():
        pass
        signal = strategy_fn(row)
        pass
        pass
        pass
        portfolio_value.append(capital)
    return portfolio_value

