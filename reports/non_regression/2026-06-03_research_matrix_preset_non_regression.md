# Non-Regression - Research Matrix Preset - 2026-06-03

Verdict: PASS

## Scope

This change standardizes the AUTOBOT research matrix workflow so the same
validation can be launched repeatedly from fresh VPS state data.

New CLI conveniences:

- `--preset autobot-top14-eur`
  - expands to the standard AUTOBOT Kraken EUR universe;
  - uses the default research strategy families `grid`, `trend`,
    `mean_reversion`;
  - can still be narrowed with explicit `--symbols` or `--strategies`.
- `--standard-reports`
  - writes the normal evidence bundle in one command:
    registry recommendations, loss attribution, setup quality,
    strategy/regime, strategy/regime baselines, strategy/regime walk-forward,
    and strategy scorecard.

## Files Changed

- `src/autobot/v2/cli.py`
  - Adds the `AUTOBOT_TOP14_EUR_SYMBOLS` constant.
  - Adds the `autobot-top14-eur` matrix preset.
  - Adds `--standard-reports`.
  - Keeps the command research-only and report-only.

- `tests/test_v2_cli.py`
  - Adds test coverage for the top-14 preset expansion.
  - Adds test coverage for `--standard-reports`.
  - Verifies generated evidence does not allow live promotion.

- `docs/research/CLI_WORKFLOWS.md`
  - Documents the repeatable standard top-14 research matrix command.
  - Documents the report bundle and safety checklist.

## What Must Not Have Changed

- Dashboard: unchanged.
- Runtime paper executor: unchanged.
- Kraken/live execution: unchanged.
- Strategy router: unchanged.
- Risk sizing/risk thresholds: unchanged.
- Existing APIs: unchanged.
- Docker/VPS behavior: unchanged.
- Persistent runtime data: unchanged.

## Trading Safety

- No live trading flag was changed.
- No order execution path was changed.
- No risk, sizing, leverage, fee, spread, slippage, or cost-guard behavior was
  changed.
- The matrix preset only configures research validation inputs.
- `--standard-reports` writes reports only.
- The strategy registry is not mutated automatically.
- Scorecards and recommendations keep `live_promotion_allowed=false`.

## Validation

Commands executed:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\cli.py tests\test_v2_cli.py
```

Result: PASS

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_v2_cli.py -q
```

Result: `9 passed in 0.28s`

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research tests\risk tests\paper tests\test_v2_cli.py -q
```

Result: `105 passed in 0.97s`

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## Runtime / VPS

No VPS restart was performed because this is an isolated research CLI workflow
change. It does not alter Docker, runtime services, dashboard APIs, paper
execution, live execution, or databases.

## Risks Remaining

- The preset standardizes the current top-14 universe; if the runtime universe
  changes, this constant should be updated deliberately and covered by a new
  non-regression report.
- The command makes the validation easier to repeat, but it does not improve
  strategy expectancy by itself.
- Fresh VPS validation still requires a current read-only copy of the state DB.

## Recommendation

Proceed to the next roadmap step: strengthen the official paper versus
research/replay comparison so strategy decisions can show whether runtime paper
trades match the research matrix conclusions.
