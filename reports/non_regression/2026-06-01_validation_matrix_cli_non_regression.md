# Non-Regression Report - Validation Matrix CLI

Date: 2026-06-01
Verdict: PASS_WITH_WARNINGS

## Scope

This change adds a command-line interface to the research validation matrix so
AUTOBOT can run a strategy-by-symbol batch and optionally emit registry
recommendation reports from the same command.

The CLI remains research-only and does not touch runtime paper/live execution.

## Files Changed

- `src/autobot/v2/research/validation_matrix.py`
  - Adds `main()` and `python -m autobot.v2.research.validation_matrix`.
  - Adds arguments for symbols, strategies, data source, cost assumptions,
    strategy configs, walk-forward settings, and optional registry
    recommendations.
  - Prints machine-readable JSON output.
- `tests/research/test_validation_matrix.py`
  - Adds CLI coverage for matrix execution plus recommendation report writing.

## What Did Not Change

- No strategy implementation changed.
- No official paper executor changed.
- No live executor changed.
- No strategy router changed.
- No risk manager changed.
- No dashboard/API runtime behavior changed.
- No persistent runtime DB writes were added.
- No registry JSON mutation is performed.

## Trading Safety Confirmation

- CLI is in `autobot.v2.research` only.
- It invokes `run_validation_matrix()` and optionally writes recommendation
  files.
- It cannot submit Kraken orders.
- It cannot change paper or live positions.
- It cannot change strategy promotion state by itself.
- Live promotion remains `false` in recommendation output.

## Validation Commands

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\validation_matrix.py tests\research\test_validation_matrix.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_validation_matrix.py tests\research\test_registry_recommendations.py -q
```

Result: PASS - `8 passed in 0.15s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: PASS - `40 passed in 0.24s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: PASS - `24 passed in 0.18s`

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## Risks / Limits

- The CLI quality still depends on the market data supplied to it.
- It does not tune parameters; it evaluates the provided strategy configs.
- Local `data/autobot_state.db` currently has no `market_price_samples`, so a
  meaningful real-data matrix requires a current VPS DB export or direct VPS
  run.

## Recommendation

Next step: run this CLI on a current AUTOBOT state DB from the VPS and use the
generated recommendation report to decide which strategy families remain
learning-only, need modification, or deserve deeper walk-forward validation.
