# Non-Regression Report - Research Lazy Imports And VPS Matrix Smoke

Date: 2026-06-01
Verdict: PASS_WITH_WARNINGS

## Scope

This change makes `autobot.v2.research` exports lazy so running research
submodules with `python -m` no longer pre-imports the target module through the
package `__init__`.

It also records a concise summary of the first validation matrix run against a
fresh read-only copy of the VPS AUTOBOT state DB.

## Files Changed

- `src/autobot/v2/research/__init__.py`
  - Converts eager research imports to lazy exports.
  - Keeps the same public names in `__all__`.
  - Avoids runpy warnings when executing research submodules as CLI modules.
- `reports/research/vps_validation_matrix_2026_06_01_summary.md`
  - Documents the first real-data matrix run over the VPS price-sample DB.
  - Captures the human-readable conclusion without committing generated cell
    journals/reports.

## What Did Not Change

- No runtime strategy logic changed.
- No official paper executor changed.
- No live executor changed.
- No order routing changed.
- No risk configuration changed.
- No dashboard/API endpoint changed.
- No strategy registry mutation occurred.
- No VPS deployment occurred.

## Trading Safety Confirmation

- The matrix run used a local read-only copy of the VPS SQLite DB.
- The research harness cannot submit orders.
- The recommendation report keeps `live_promotion_allowed=false`.
- The registry was not automatically updated.
- No live behavior was changed.

## Validation Commands

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\__init__.py src\autobot\v2\research\validation_matrix.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: PASS - `40 passed in 0.26s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: PASS - `24 passed in 0.17s`

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m autobot.v2.research.validation_matrix --run-id smoke_cli_no_warning --data-source autobot_state_db --data-path data\vps_autobot_state_2026-06-01.db --symbols TRXEUR --strategies grid --output-dir reports\research_matrix\smoke_cli_no_warning --min-closed-trades 1
```

Result: PASS - CLI completed without the previous runpy warning.

## VPS Matrix Observation

The full 14-symbol matrix completed with:

- 42 cells.
- 42 successful cells.
- 0 errors.
- 0 strategy families passing recommendation criteria.

All three tested families (`grid`, `trend`, `mean_reversion`) were negative in
aggregate after costs. See
`reports/research/vps_validation_matrix_2026_06_01_summary.md`.

## Warnings / Limits

- The VPS matrix used runtime price samples, not full exchange OHLCV plus order
  book depth.
- The generated detailed matrix output was intentionally not committed to keep
  the repository light.
- This is backtest-mode evidence only; next work should add richer data and
  walk-forward runs before making registry status edits.

## Recommendation

Use the summary as a diagnostic: current default research configurations should
remain blocked from promotion. The next useful engineering task is per-strategy
loss attribution on the matrix output: entry timing, exit timing, TP/SL distance,
cost drag, and regime at entry.
