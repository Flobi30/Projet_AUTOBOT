# Non-Regression - Trend Research Exit Modes - 2026-06-02

Verdict: `PASS_WITH_WARNINGS`

## Scope

This check covers the research-only change adding configurable exit experiments to `TrendResearchSignalGenerator`.

## Files Changed

- `src/autobot/v2/research/strategy_signal_generators.py`
  - Added `TrendResearchConfig.exit_mode` with research-only modes:
    - `baseline`
    - `cost_buffer_tp`
    - `mfe_trailing`
    - `time_stop`
  - Added metadata for trend exits:
    - `exit_mode`
    - `bars_in_position`
    - `highest_profit_bps`
    - `giveback_bps`
  - Default remains `baseline`, preserving existing behavior unless a validation run explicitly passes a different config.

- `tests/research/test_strategy_signal_generators.py`
  - Added coverage proving each new research-only exit mode can close a validation trade.
  - Added assertions that every tested mode keeps `live_promotion_allowed` false.

## Modules Not Changed

- Runtime paper trading: not modified.
- Live execution: not modified.
- Kraken integration: not modified.
- Risk manager/runtime router: not modified.
- Dashboard/API: not modified.
- Persistent data and Docker/VPS runtime: not modified.

## Trading Safety

- No live flag was changed.
- No order router was changed.
- No production paper executor was changed.
- The new modes only affect the isolated research signal generator used by replay/backtest validation.
- Strategy promotion remains governed by existing registry and validation gates.

## Validation Evidence

Commands run locally:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\strategy_signal_generators.py tests\research\test_strategy_signal_generators.py
```

Result: pass.

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_strategy_signal_generators.py tests\research\test_validation_runner.py -q
```

Result: `10 passed in 0.14s`.

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: `47 passed in 0.25s`.

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: `24 passed in 0.33s`.

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: pass.

## Research Replay Evidence

After local tests passed, a research-only trend exit comparison was run on the local VPS-derived dataset:

- Dataset: `data/vps_autobot_state_2026-06-01.db`
- Source table: `market_price_samples`
- Symbols: 14 non-duplicated dashboard symbols
- Strategy: `trend`
- Modes compared:
  - `baseline`
  - `cost_buffer_tp`
  - `mfe_trailing`
  - `time_stop`

Summary report:

- `reports/research/vps_trend_exit_experiment_2026_06_02_summary.md`

Outcome:

- No tested exit-only policy improved net PnL.
- `cost_buffer_tp` worsened net PnL from `-115.803564` EUR to `-150.265157` EUR.
- `mfe_trailing` worsened net PnL from `-115.803564` EUR to `-126.223463` EUR.
- `time_stop` was effectively equivalent to baseline with this parameterization.
- Recommendation: do not promote these exit policies to official paper execution; move next research toward trend entry/regime quality.

## VPS Runtime

Not checked in this slice because the change has not been deployed and does not modify runtime/Docker/backend API behavior. VPS runtime should be checked after any deployment or runtime-facing change.

## Risks Remaining

- These modes are now technically testable, but their usefulness is not proven until replayed on the VPS-derived historical dataset.
- `cost_buffer_tp`, `mfe_trailing`, and `time_stop` are research configurations, not production execution policies.
- No claim is made that they improve PnL until matrix comparison reports confirm it after fees/spread/slippage.

## Next Recommended Action

Add a trend setup-quality diagnostic focused on entry/regime evidence instead of promoting an exit-only tweak:

- breakout strength
- momentum persistence
- ATR regime
- spread/cost ratio
- post-entry MFE distribution
- stop-hit frequency
