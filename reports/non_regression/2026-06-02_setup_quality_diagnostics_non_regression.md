# Non-Regression - Setup Quality Diagnostics - 2026-06-02

Verdict: `PASS_WITH_WARNINGS`

## Scope

This check covers the research-only setup-quality diagnostic added to explain whether trend entries are strong enough before costs.

## Files Changed

- `src/autobot/v2/research/setup_quality.py`
  - New diagnostic module for grouping research trade journals by:
    - market regime
    - breakout strength
    - momentum strength
    - ATR regime
  - Tracks:
    - cost-dominated trades
    - trades where MFE exceeded cost but final net PnL was still negative
    - average MFE/MAE/exit capture by bucket

- `src/autobot/v2/research/__init__.py`
  - Exposes setup-quality helpers through the lazy research package exports.

- `tests/research/test_setup_quality.py`
  - Adds unit tests for setup buckets and report writing.

- `reports/research/vps_2026_06_02_trend_setup_quality_setup_quality.md`
- `reports/research/vps_2026_06_02_trend_setup_quality_setup_quality.json`
  - Permanent research report generated from local VPS-derived trend baseline data.

## Modules Not Changed

- Runtime paper trading: not modified.
- Live execution: not modified.
- Kraken integration: not modified.
- Strategy router: not modified.
- Risk manager: not modified.
- Dashboard/API: not modified.
- Persistent VPS data: not modified.

## Trading Safety

- The new diagnostic reads research journals only.
- It does not place orders.
- It does not change sizing, fees, spread, slippage, router, risk, or registry gates.
- It does not promote any strategy.
- Live trading remains untouched and disabled.

## Validation Evidence

Commands run locally:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\setup_quality.py tests\research\test_setup_quality.py src\autobot\v2\research\__init__.py
```

Result: pass.

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_setup_quality.py -q
```

Result: `2 passed in 0.06s`.

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: `49 passed in 0.43s`.

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: `24 passed in 0.17s`.

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: pass.

## Research Evidence

The setup-quality diagnostic was run on a local replay of the VPS-derived trend baseline:

- Source: `data/vps_autobot_state_2026-06-01.db`
- Symbols: 14 non-duplicated dashboard symbols
- Strategy: `trend`
- Trades analyzed: `221`
- Gross PnL: `-45.083564` EUR
- Net PnL: `-115.803564` EUR
- Cost-dominated trades: `140`
- MFE-above-cost lost trades: `43`

Worst buckets:

- Breakout: `weak_lt_40`, `146` trades, `-72.677642` EUR net, win rate `15.7534%`.
- Momentum: `medium_40_100`, `114` trades, `-54.839891` EUR net, win rate `14.9123%`.
- ATR: `medium_15_50`, `144` trades, `-70.164125` EUR net, win rate `22.9167%`.

## Risks Remaining

- Regime field is currently `unknown` for this VPS-derived replay, so regime-level conclusions are not yet available.
- The diagnostic proves where trend entries lose money; it does not yet enforce stricter entries.
- The thresholds are explanatory buckets, not production trading rules.

## Next Recommended Action

Use this evidence to create a research-only trend entry filter experiment:

- reject weak breakout entries below a configurable threshold;
- require momentum persistence, not just one breakout;
- require ATR and MFE/cost context strong enough to survive fees/spread/slippage;
- rerun matrix comparison before touching official paper execution.
