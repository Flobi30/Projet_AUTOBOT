# Non-Regression Report - Walk-Forward And Baseline Upgrade

Date: 2026-05-31
Verdict: PASS_WITH_WARNINGS

## Scope

This change advances the research roadmap only. It strengthens the isolated
research backtest stack by adding a deterministic random baseline and a
walk-forward validator. Runtime paper trading, live trading, Kraken access,
dashboard routes, Docker configuration, and persistent production data are not
modified.

## Files Changed

- `src/autobot/v2/research/backtest_engine.py`
  - Adds `random_signal_same_frequency` baseline.
  - Compares strategy metrics against the strongest available baseline instead
    of only buy-and-hold.
  - Keeps live promotion impossible.
- `src/autobot/v2/research/walk_forward.py`
  - Adds `WalkForwardValidator` and report rendering.
  - Splits bars into train/test windows.
  - Replays only the test window to avoid passing future or train data into the
    strategy during validation.
- `src/autobot/v2/research/__init__.py`
  - Exports the walk-forward types.
- `tests/research/test_backtest_engine.py`
  - Covers deterministic random baseline behavior.
- `tests/research/test_walk_forward.py`
  - Covers test-window-only history, insufficient folds, passing folds, reports
    and live-safety flags.

## What Did Not Change

- No official paper execution path changed.
- No live execution path changed.
- No strategy router changed.
- No risk manager changed.
- No dashboard/API runtime route changed.
- No Docker/VPS runtime state changed.
- No existing persisted trading DB was read or written by the new code.

## Trading Safety Confirmation

- The walk-forward validator is research-only.
- It cannot submit Kraken orders.
- It does not update the strategy registry automatically.
- It cannot promote a strategy live.
- `live_promotion_allowed` remains `False` in all new decisions.
- No candidate, learning, shadow-only, or backtest-passed strategy can bypass
  the existing promotion gate through this code.

## Validation Commands

```powershell
python -m py_compile src\autobot\v2\research\backtest_engine.py src\autobot\v2\research\walk_forward.py tests\research\test_backtest_engine.py tests\research\test_walk_forward.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research -q
```

Result: PASS - `21 passed in 0.22s`

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

- This is still a bar-level research validator, not a full order-book/tick
  simulation.
- Walk-forward currently validates fixed strategy parameters; it does not yet
  optimize on train and test out-of-sample parameter selections.
- Random baseline is deterministic and useful as a guardrail, but it is not a
  replacement for richer bootstrap/permutation testing.
- No VPS runtime check was performed because the change is local research code
  and does not alter the running bot.

## Recommendation

Next step: connect the new research stack to real AUTOBOT replay datasets and
standardize strategy adapters so grid/trend/mean-reversion can be measured
through the same contract before any new strategy work.
