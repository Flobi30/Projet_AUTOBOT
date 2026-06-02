# Non-Regression Report - Strategy Regime Comparison - 2026-06-02

## Verdict

PASS_WITH_WARNINGS

## Scope

This change adds research-only strategy-by-regime diagnostics to AUTOBOT's validation tooling.

## Files Changed

- `src/autobot/v2/research/strategy_regime_report.py`
  - New research-only report module grouping validation trade journals by `strategy_id` and `regime`.
  - Adds costs, net PnL, MFE/cost, exit capture, and cost-dominated diagnostics.
- `src/autobot/v2/research/validation_matrix.py`
  - Adds CLI flag `--write-strategy-regime`.
  - Writes a strategy x regime report from matrix cell journals.
- `src/autobot/v2/research/__init__.py`
  - Adds lazy exports for the new research report helpers.
- `tests/research/test_strategy_regime_report.py`
  - Adds unit coverage for grouping and report writing.
- `tests/research/test_validation_matrix.py`
  - Extends CLI coverage to ensure the strategy-regime report is generated.
- `reports/research/vps_2026_06_02_strategy_regime_comparison/*`
  - Permanent combined research report and JSON output.
- `reports/research/vps_strategy_regime_comparison_2026_06_02_summary.md`
  - Human-readable performance summary.
- `reports/research/autobot_performance_audit_for_gpt55_2026_06_02.md`
  - Adds the latest strategy x regime comparison to the external audit prompt.

## What Did Not Change

- Live trading activation: unchanged.
- Kraken order routing: unchanged.
- Official paper execution: unchanged.
- Runtime strategy router: unchanged.
- Risk management and sizing: unchanged.
- Dashboard/API runtime behavior: unchanged.
- Persistent trading data: unchanged.
- Docker/VPS runtime: not redeployed in this change.

## Trading Safety

- No strategy was promoted.
- No candidate was authorized for live.
- No paper/live execution path was modified.
- No permissive fallback was added.
- The new module only reads validation journals and writes research reports.

## Test Evidence

Focused tests run before this report:

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_strategy_regime_report.py tests\research\test_validation_matrix.py -q
```

Result:

```text
4 passed in 0.18s
```

Broader research suite:

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result:

```text
55 passed in 0.32s
```

Python compile sweep:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result:

```text
PASS
```

Historical harness/registry non-regression:

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result:

```text
24 passed in 0.18s
```

## Risks / Warnings

- The generated report uses the current research replay journals only. It does not prove official paper behavior by itself.
- The regime classifier is a diagnostic sensor, not a predictive model.
- Positive buckets are too small to promote:
  - trend `chaos`: 24 trades, net `+1.236346 EUR`;
  - mean-reversion `high_vol`: 4 trades, net `+0.714304 EUR`.
- The main research conclusion is negative: all tested strategy families are still net negative overall.

## Recommendation

Proceed to the next research-validation step only after tests remain green:

1. Add baseline comparisons by strategy/regime.
2. Add walk-forward splits.
3. Reconcile official paper ledger vs research replay.
4. Keep live disabled.
