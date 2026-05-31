# Non-Regression Report - Market Data SQLite Loader

Date: 2026-05-31
Verdict: PASS_WITH_WARNINGS

## Scope

This change lets the isolated research `MarketDataRepository` load AUTOBOT
runtime price samples from `autobot_state.db` in read-only mode. It supports the
roadmap requirement to validate strategies on real AUTOBOT replay data instead
of synthetic-only CSV fixtures.

## Files Changed

- `src/autobot/v2/research/market_data_repository.py`
  - Adds `load_autobot_state_db()`.
  - Reads `market_price_samples` through SQLite URI `mode=ro`.
  - Converts tick-like samples into one-price OHLC `MarketBar` rows.
  - Supports symbol, symbols, start/end, and limit filters.
- `tests/research/test_market_data_repository.py`
  - Covers state DB sample loading, ordering, metadata, and missing-table
    behavior.

## What Did Not Change

- No production persistence code changed.
- No runtime data writes were added.
- No paper/live execution path changed.
- No strategy/router/risk/dashboard runtime behavior changed.
- No Docker/VPS runtime state changed.

## Trading Safety Confirmation

- Loader is read-only.
- Loader cannot submit orders.
- Loader cannot promote strategies.
- Loader cannot mutate AUTOBOT state databases.
- Live trading remains untouched.

## Validation Commands

```powershell
python -m py_compile src\autobot\v2\research\market_data_repository.py tests\research\test_market_data_repository.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research -q
```

Result: PASS - `25 passed in 0.23s`

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: PASS - `24 passed in 0.24s`

```powershell
python -m compileall -q src
```

Result: PASS

Note: Python bytecode cache files touched by compile/test execution were restored
from Git so the final diff contains only source/tests/report changes.

## Risks / Limits

- Runtime price samples are tick-like, not full OHLCV candles; volume is set to
  `0.0`.
- Order-book depth, bid/ask and spread are not present in `market_price_samples`.
- The next step should add optional resampling/aggregation if candle-level
  indicators require it.

## Recommendation

Use this loader as the first real data bridge for the research backtest stack.
Then add a CLI/report command that can run a strategy adapter against a selected
symbol and time window from `autobot_state.db`.
