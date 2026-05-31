# Non-Regression Report - Research Strategy Adapter

Date: 2026-05-31
Verdict: PASS_WITH_WARNINGS

## Scope

This change adds a research-only adapter layer between AUTOBOT runtime
`TradingSignal` objects and the isolated research `BacktestSignal` contract. It
does not connect any production strategy to official paper or live execution.

## Files Changed

- `src/autobot/v2/research/strategy_adapters.py`
  - Adds `TradingSignalAdapter` for `TradingSignal -> BacktestSignal`.
  - Adds `RuntimeStrategyBacktestAdapter` for synchronous runtime strategies in
    research replay only.
  - Adds `ResearchStrategyInstance`, a minimal fake instance for research tests.
- `src/autobot/v2/research/__init__.py`
  - Exports the adapter types.
- `tests/research/test_strategy_adapters.py`
  - Covers BUY/SELL/CLOSE/HOLD conversion and callback signal collection.

## What Did Not Change

- No strategy implementation changed.
- No strategy router changed.
- No official paper executor changed.
- No live executor changed.
- No risk, sizing, leverage, stop-loss, take-profit or kill-switch code changed.
- No dashboard/API runtime route changed.
- No Docker/VPS runtime state changed.

## Trading Safety Confirmation

- The adapter is research-only.
- It does not execute orders.
- It does not update live/paper positions.
- It does not promote strategies.
- It does not bypass the promotion gate.
- It only translates emitted signals into the backtest contract.

## Validation Commands

```powershell
python -m py_compile src\autobot\v2\research\strategy_adapters.py tests\research\test_strategy_adapters.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research -q
```

Result: PASS - `23 passed in 0.22s`

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: PASS - `24 passed in 0.23s`

```powershell
python -m compileall -q src
```

Result: PASS

Note: Python bytecode cache files touched by compile/test execution were restored
from Git so the final diff contains only source/tests/report changes.

## Risks / Limits

- The adapter currently wraps synchronous callback-style strategies. Async
  strategies need a separate adapter.
- Runtime strategies may maintain position state internally; the current adapter
  translates signals but does not yet feed fills back into those strategies.
- Production grid/trend/mean-reversion have not yet been batch-tested through
  this adapter.

## Recommendation

Next step: add controlled, strategy-specific adapters or signal-generator
wrappers for grid/trend/mean-reversion and run them through the backtest and
walk-forward validators on real AUTOBOT replay datasets.
