# Non-Regression Report - Loss Attribution

Date: 2026-06-01
Verdict: PASS_WITH_WARNINGS

## Scope

This change adds a research-only loss attribution helper for AUTOBOT trade
journals. It explains whether negative research results are caused by raw signal
quality, fees, spread, slippage, exit reasons, entry reasons, or one dominant
symbol.

## Files Changed

- `src/autobot/v2/research/loss_attribution.py`
  - Adds `analyze_trade_losses()`.
  - Adds `analyze_trade_journal()`.
  - Adds JSON/Markdown report writing.
  - Tracks cost-flipped trades where gross PnL is positive but net PnL is
    negative after costs.
- `src/autobot/v2/research/__init__.py`
  - Exports loss attribution helpers lazily.
- `tests/research/test_loss_attribution.py`
  - Covers cost drag, cost-flipped trades, buckets by symbol/reason, and report
    writing.

## What Did Not Change

- No strategy logic changed.
- No official paper executor changed.
- No live executor changed.
- No order routing changed.
- No risk sizing changed.
- No dashboard/API runtime behavior changed.
- No persistent runtime DB writes were added.

## Trading Safety Confirmation

- Loss attribution reads research `TradeJournal` data only.
- It cannot create orders.
- It cannot promote strategies.
- It cannot mutate the strategy registry.
- It does not touch paper/live execution.

## Validation Commands

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\loss_attribution.py tests\research\test_loss_attribution.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_loss_attribution.py -q
```

Result: PASS - `2 passed in 0.08s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: PASS - `42 passed in 0.26s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: PASS - `24 passed in 0.18s`

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## Risks / Limits

- Attribution quality depends on the journal fields populated by the backtest
  or replay.
- It is diagnostic only; it does not yet feed automatic parameter changes.
- It does not replace walk-forward validation.

## Recommendation

Use this on losing matrix cells to separate signal problems from cost problems.
The next useful step is to batch-generate attribution summaries for the worst
cells from the VPS matrix and use those facts before changing strategy logic.
