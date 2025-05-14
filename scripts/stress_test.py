"""
Stress test script to simulate a flash crash and analyze its impact.
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

def download_historical_data(symbol="BTC-USD", days=30):
    """Simulate downloading historical data."""
    dates = pd.date_range(end=datetime.now(), periods=days*1440, freq='min')

    np.random.seed(42)  # For reproducibility
    price = 30000 + np.random.normal(0, 100, size=len(dates)).cumsum()
    price = np.abs(price)  # Ensure prices are positive

    df = pd.DataFrame({
        'timestamp': dates,
        'price': price,
        'volume': np.random.exponential(100, size=len(dates))
    })

    return df

def introduce_flash_crash(df, drop_percent=-20, crash_duration_minutes=15):
    """Introduce a flash crash at a random point in the data."""
    df_crash = df.copy()

    crash_start_idx = np.random.randint(1440, len(df) - 1440)

    crash_indices = range(crash_start_idx, crash_start_idx + crash_duration_minutes)

    for i, idx in enumerate(crash_indices):
        progress = i / crash_duration_minutes
        if progress < 0.5:
            factor = 1 + (drop_percent/100) * (progress * 2)
        else:
            recovery_percent = drop_percent * 0.6  # Recover 60% of the drop
            factor = 1 + (drop_percent/100) + (recovery_percent/100) * ((progress - 0.5) * 2)

        df_crash.loc[idx, 'price'] = df.loc[idx, 'price'] * factor
        df_crash.loc[idx, 'volume'] = df.loc[idx, 'volume'] * 3

    return df_crash, crash_start_idx, crash_start_idx + crash_duration_minutes

def run_backtest(df, initial_balance=10000):
    """Run a simple backtest to measure drawdown and P&L."""
    balance = initial_balance
    positions = 0
    equity_curve = []

    for i in range(5, len(df)):
        price = df.iloc[i]['price']
        prev_price = df.iloc[i-5]['price']
        price_change = (price - prev_price) / prev_price * 100

        equity = balance + positions * price
        equity_curve.append(equity)

        if price_change < -5 and positions == 0:
            positions = balance * 0.95 / price  # Use 95% of balance
            balance = balance * 0.05  # Keep 5% as reserve

        elif positions > 0 and (price_change > 2 or price_change < -10):
            balance += positions * price
            positions = 0

    final_equity = balance + positions * df.iloc[-1]['price']

    peak = max(equity_curve)
    drawdown = min([100 * (peak - eq) / peak for eq in equity_curve])

    return {
        'initial_balance': initial_balance,
        'final_equity': final_equity,
        'pnl': final_equity - initial_balance,
        'pnl_percent': (final_equity - initial_balance) / initial_balance * 100,
        'max_drawdown_percent': drawdown,
        'equity_curve': equity_curve
    }

def plot_equity_curves(normal_df, crash_df, normal_results, crash_results,
                       crash_start, crash_end):
    """Plot equity curves before and after introducing the flash crash."""
    plt.figure(figsize=(12, 8))

    plt.subplot(2, 1, 1)
    plt.plot(normal_df['price'], label='Normal Price')
    plt.plot(crash_df['price'], label='Crash Price', alpha=0.7)
    plt.axvspan(crash_start, crash_end, color='red', alpha=0.3, label='Flash Crash')
    plt.title('Price Comparison')
    plt.legend()
    plt.grid(True)

    plt.subplot(2, 1, 2)
    plt.plot(normal_results['equity_curve'], label='Normal Equity')
    plt.plot(crash_results['equity_curve'], label='Crash Equity')
    plt.axvspan(crash_start, crash_end, color='red', alpha=0.3, label='Flash Crash')
    plt.title('Equity Curve Comparison')
    plt.legend()
    plt.grid(True)

    plt.tight_layout()

    os.makedirs('results', exist_ok=True)

    plt.savefig('results/flash_crash_test.png')
    plt.close()

def main():
    """Main function to run the stress test."""
    print("Starting flash crash stress test...")

    print("Downloading historical data...")
    df = download_historical_data()

    print("Running backtest on normal data...")
    normal_results = run_backtest(df)

    print("Introducing flash crash...")
    crash_df, crash_start, crash_end = introduce_flash_crash(df)

    print("Running backtest on crash data...")
    crash_results = run_backtest(crash_df)

    print("Plotting equity curves...")
    plot_equity_curves(df, crash_df, normal_results, crash_results,
                      crash_start, crash_end)

    summary = {
        'normal': {
            'final_equity': normal_results['final_equity'],
            'pnl_percent': normal_results['pnl_percent'],
            'max_drawdown_percent': normal_results['max_drawdown_percent']
        },
        'crash': {
            'final_equity': crash_results['final_equity'],
            'pnl_percent': crash_results['pnl_percent'],
            'max_drawdown_percent': crash_results['max_drawdown_percent']
        },
        'impact': {
            'equity_difference': crash_results['final_equity'] - normal_results['final_equity'],
            'equity_difference_percent': (crash_results['final_equity'] - normal_results['final_equity']) / normal_results['final_equity'] * 100,
            'drawdown_difference': crash_results['max_drawdown_percent'] - normal_results['max_drawdown_percent']
        }
    }

    with open('results/flash_crash_summary.json', 'w') as f:
        json.dump(summary, f, indent=4)

    print("Stress test completed!")
    print(f"Results saved to results/flash_crash_test.png and results/flash_crash_summary.json")

    return summary

if __name__ == "__main__":
    main()

