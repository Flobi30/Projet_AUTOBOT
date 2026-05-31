# Non-Regression Report - Research Validation Runner

Date: 2026-05-31
Verdict: PASS_WITH_WARNINGS

## Scope

This change adds a research-only runner/CLI for AUTOBOT validation. It can load
CSV or read-only `autobot_state.db` market samples, choose one of the existing
strategy-family signal generators, then run either a backtest or walk-forward
validation with reports.

It does not alter runtime paper/live trading.

## Files Changed

- `src/autobot/v2/research/validation_runner.py`
  - Adds `ValidationRunnerConfig`.
  - Adds `run_validation()`.
  - Adds CLI entrypoint via `python -m autobot.v2.research.validation_runner`.
  - Supports strategies: `grid`, `trend`, `mean_reversion`.
  - Supports data sources: `csv`, `autobot_state_db`.
  - Supports modes: `backtest`, `walk_forward`.
- `src/autobot/v2/research/__init__.py`
  - Exports runner types and `run_validation`.
- `tests/research/test_validation_runner.py`
  - Covers CSV backtest.
  - Covers CSV walk-forward.
  - Covers CLI JSON output.

## What Did Not Change

- No production strategy code changed.
- No official paper executor changed.
- No live executor changed.
- No strategy router changed.
- No risk manager changed.
- No dashboard/API runtime behavior changed.
- No Docker/VPS runtime state changed.
- No production DB writes were added.

## Trading Safety Confirmation

- Runner is research-only.
- Runner cannot submit Kraken orders.
- Runner only writes reports under its output directory.
- Runner does not mutate the strategy registry.
- Runner does not mutate paper/live positions.
- Runner does not bypass promotion gates.
- Live trading remains untouched and not enabled.

## Validation Commands

```powershell
python -m py_compile src\autobot\v2\research\validation_runner.py tests\research\test_validation_runner.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research -q
```

Result: PASS - `32 passed in 0.29s`

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

- Runner validates research generators, not exact production async strategy
  internals.
- Real AUTOBOT SQLite samples may be tick-like and lack bid/ask/order-book
  details.
- No batch matrix runner exists yet for all symbols and all strategy families.
- No automatic registry update is performed.

## Recommendation

Next step: add a batch validation matrix that runs all three strategy families
over selected symbols from `autobot_state.db`, aggregates results, and produces a
single comparison report suitable for registry decisions.
