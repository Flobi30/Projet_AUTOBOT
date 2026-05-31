# Non-Regression Report - Research Signal Generators

Date: 2026-05-31
Verdict: PASS_WITH_WARNINGS

## Scope

This change adds research-only signal generators for the existing AUTOBOT
strategy families: grid, trend/momentum, and mean-reversion. They let the
isolated `BacktestEngine` and `WalkForwardValidator` measure these families
under the same cost/baseline contract.

This does not replace production strategies and does not route anything to
official paper or live execution.

## Files Changed

- `src/autobot/v2/research/strategy_signal_generators.py`
  - Adds `GridResearchSignalGenerator`.
  - Adds `TrendResearchSignalGenerator`.
  - Adds `MeanReversionResearchSignalGenerator`.
  - Adds typed config dataclasses for each generator.
- `src/autobot/v2/research/__init__.py`
  - Exports the research signal generator classes.
- `tests/research/test_strategy_signal_generators.py`
  - Covers grid support entry/take-profit behavior.
  - Covers trend breakout/reversal behavior.
  - Covers mean-reversion z-score entry/exit behavior.
  - Covers strategy-family metadata used by validation reports.

## What Did Not Change

- No production grid/trend/mean-reversion strategy code changed.
- No official paper execution path changed.
- No live execution path changed.
- No strategy router changed.
- No risk manager or sizing code changed.
- No dashboard/API runtime route changed.
- No Docker/VPS runtime state changed.
- No persisted trading DB was read or written.

## Trading Safety Confirmation

- The generators are research-only.
- They return `BacktestSignal` objects only.
- They cannot submit Kraken orders.
- They cannot update official paper positions.
- They cannot promote a strategy.
- They cannot bypass the existing promotion gate.
- `live_promotion_allowed` remains false in the tested backtest decisions.

## Validation Commands

```powershell
python -m py_compile src\autobot\v2\research\strategy_signal_generators.py tests\research\test_strategy_signal_generators.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\research -q
```

Result: PASS - `29 passed in 0.26s`

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: PASS - `24 passed in 0.26s`

```powershell
python -m compileall -q src
```

Result: PASS

Note: Python bytecode cache files touched by compile/test execution were restored
from Git so the final diff contains only source/tests/report changes.

## Risks / Limits

- These are validation adapters for strategy families, not exact one-to-one
  clones of every production/shadow variant.
- Grid/trend/mean-reversion still need batch replay on real AUTOBOT data before
  any conclusion about profitability.
- Trend and mean-reversion generators use bar-level closes; order-book/tick
  fill precision remains a later improvement.
- No automated registry update is performed.

## Recommendation

Next step: run these generators against real `market_price_samples` via
`MarketDataRepository.load_autobot_state_db()`, generate comparable reports per
symbol/strategy family, and feed only the resulting evidence into the registry.
