
import pandas as pd
import numpy as np


def run_backtest(df, strategy_fn, initial_capital=500):
    """Exécute un backtest simple"""
    pass
    if df is None or len(df) == 0:
        raise ValueError("Les données sont vides.")
    
    pass
    signals = strategy_fn(df)
    if signals is None or len(signals) == 0:
        raise ValueError("Les signaux sont vides.")
pass
    pass
    df['strategy_signal'] = signals
    df['daily_return'] = df['close'].pct_change()
    df['strategy_return'] = df['daily_return'] * df['strategy_signal'].shift(1)
    df['equity'] = initial_capital * (1 + df['strategy_return']).cumprod()
pass
    pass
    total_pnl = df['equity'].iloc[-1] - initial_capital
pass
    pass
    df['cum_max'] = df['equity'].cummax()
    df['drawdown'] = df['cum_max'] - df['equity']
    max_drawdown = df['drawdown'].max()
pass
    pass
    sharpe_ratio = (df['strategy_return'].mean() / df['strategy_return'].std()) *         np.sqrt(252) if df['strategy_return'].std() != 0 else np.nan
pass
    return {
        'final_equity': df['equity'].iloc[-1],
        'total_pnl': total_pnl,
        'max_drawdown': max_drawdown,
        'sharpe_ratio': sharpe_ratio,
        'equity_curve': df['equity'],
    }

