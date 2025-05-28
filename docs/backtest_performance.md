# Généré automatiquement depuis : refactor_backtest.md

# prompts/refactor_backtest.md

## System
You are GPT‑Code, expert in quantitative finance code. Refactor the backtest module.

## User
1. Generate a new package `backtest/` with:
   - `run_backtest(df, strategy_fn, initial_capital)`  
   - Calculation of P&L, drawdown, Sharpe ratio.
2. Optimize performance: vectorize loops, add caching.
3. Write unit tests covering edge cases (zero-length, NaNs).
4. Provide a brief performance report (before vs after).

## Output
- Files under `src/backtest/`: `backtest.py`, `metrics.py`, `__init__.py`.
- Tests under `tests/test_backtest.py`.
- `docs/backtest_performance.md`.
