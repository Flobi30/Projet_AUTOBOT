# prompts/stress_test.md

## System
You are a quantitative risk engineer. Simulate a flash crash.

## User
1. Download historical BTC-USD minute data.
2. Introduce a random –20% drop.
3. Run backtest to measure drawdown and P&L.
4. Plot equity curve before/after.
5. Save `flash_crash_test.png` and `flash_crash_summary.json`.

## Output
- `scripts/stress_test.py`
- `results/flash_crash_test.png`
- `results/flash_crash_summary.json`
