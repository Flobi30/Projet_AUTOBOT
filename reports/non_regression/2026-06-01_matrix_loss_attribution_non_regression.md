# Non-Regression Report - Matrix Loss Attribution

Date: 2026-06-01
Verdict: PASS_WITH_WARNINGS

## Scope

This change extends the research-only loss attribution tooling so it can process
an entire validation matrix and summarize why strategy-symbol cells lose money.

It also adds an optional CLI flag:

```powershell
--write-loss-attribution
```

This flag writes matrix-level and cell-level attribution reports beside the
matrix output. It does not touch runtime paper/live execution.

## Files Changed

- `src/autobot/v2/research/loss_attribution.py`
  - Adds `MatrixCellLossAttribution`.
  - Adds `MatrixLossAttributionReport`.
  - Adds `write_matrix_loss_attribution_report()`.
  - Adds `render_matrix_loss_attribution_report()`.
  - Infers cell journal paths from matrix report paths.
- `src/autobot/v2/research/validation_matrix.py`
  - Adds `--write-loss-attribution`.
- `src/autobot/v2/research/__init__.py`
  - Exports attribution helpers lazily.
- `tests/research/test_loss_attribution.py`
  - Adds matrix attribution coverage.
- `tests/research/test_validation_matrix.py`
  - Verifies the CLI can emit loss attribution alongside registry
    recommendations.
- `reports/research/vps_loss_attribution_2026_06_01_summary.md`
  - Captures the current VPS research finding without committing generated
    matrix artifacts.

## What Did Not Change

- No runtime strategy implementation changed.
- No official paper executor changed.
- No live executor changed.
- No order routing changed.
- No risk sizing changed.
- No dashboard/API behavior changed.
- No strategy registry mutation occurred.
- No VPS deployment occurred.

## Trading Safety Confirmation

- Matrix attribution reads research trade journals only.
- It cannot create, modify, or submit orders.
- It cannot promote strategies.
- It cannot mutate `strategy_hypotheses.json`.
- It does not alter paper/live behavior.
- Live remains disabled and untouched.

## Validation Commands

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\loss_attribution.py src\autobot\v2\research\validation_matrix.py tests\research\test_loss_attribution.py tests\research\test_validation_matrix.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_loss_attribution.py tests\research\test_validation_matrix.py -q
```

Result: PASS - `6 passed in 0.18s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: PASS - `43 passed in 0.28s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: PASS - `24 passed in 0.18s`

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## VPS Attribution Run

The generated matrix artifacts were removed from the working tree after
summarizing them to keep Git light.

Summary retained:

- `reports/research/vps_loss_attribution_2026_06_01_summary.md`

Key observation:

- 1,318 research trades.
- Gross PnL before modeled costs: `-237.923673`.
- Net PnL after costs: `-659.683673`.
- Modeled costs: `632.640000`.
- Cost-flipped trades: `301`.

## Risks / Limits

- Attribution is only as good as the research journal fields.
- The VPS run still uses runtime price samples, not full bid/ask/depth history.
- This explains losses but does not yet fix strategy logic.

## Recommendation

Next step: add trade-path diagnostics such as maximum favorable excursion,
maximum adverse excursion, TP distance versus cost distance, and hold-duration
analysis. That will show whether the core problem is entry timing, exit timing,
or targets too small relative to costs.
