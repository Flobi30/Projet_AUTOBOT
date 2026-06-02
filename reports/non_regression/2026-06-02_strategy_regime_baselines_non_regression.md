# Non-Regression Report - Strategy Regime Baselines - 2026-06-02

## Verdict

PASS_WITH_WARNINGS

## Scope

This change adds research-only baseline comparisons for strategy/regime buckets.

## Files Changed

- `src/autobot/v2/research/strategy_regime_baselines.py`
  - New baseline comparison module for strategy/regime buckets.
  - Adds `no_trade`, `buy_and_hold_regime_segments`, and deterministic `random_signal_same_frequency_regime` baselines.
  - Adds a CLI entry point for generating baseline reports from an existing strategy/regime report and market data.
- `src/autobot/v2/research/strategy_regime_report.py`
  - Adds `load_strategy_regime_report()` so generated JSON reports can be reused by later validation stages.
- `src/autobot/v2/research/validation_matrix.py`
  - Adds optional CLI flag `--write-strategy-regime-baselines`.
- `src/autobot/v2/research/__init__.py`
  - Adds lazy exports for the baseline comparison helpers.
- `tests/research/test_strategy_regime_baselines.py`
  - Adds unit coverage for baseline comparison and report writing.
- `tests/research/test_strategy_regime_report.py`
  - Adds JSON reload coverage.
- `tests/research/test_validation_matrix.py`
  - Extends CLI coverage for strategy/regime baseline report generation.
- `reports/research/vps_2026_06_02_strategy_regime_baselines/*`
  - Adds permanent baseline comparison report and JSON output.
- `reports/research/vps_strategy_regime_baselines_2026_06_02_summary.md`
  - Adds human-readable summary of baseline findings.
- `reports/research/autobot_performance_audit_for_gpt55_2026_06_02.md`
  - Updates the copy/paste audit with baseline evidence.

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
- The new module only reads validation reports, reads historical bars, and writes research reports.

## Test Evidence

Compile:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\strategy_regime_report.py src\autobot\v2\research\strategy_regime_baselines.py src\autobot\v2\research\validation_matrix.py src\autobot\v2\research\__init__.py tests\research\test_strategy_regime_baselines.py tests\research\test_strategy_regime_report.py tests\research\test_validation_matrix.py
```

Result:

```text
PASS
```

Focused tests:

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_strategy_regime_baselines.py tests\research\test_strategy_regime_report.py tests\research\test_validation_matrix.py -q
```

Result:

```text
6 passed in 0.16s
```

Full research tests:

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result:

```text
57 passed in 0.41s
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

Report generation:

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m autobot.v2.research.strategy_regime_baselines --strategy-regime-report reports\research\vps_2026_06_02_strategy_regime_comparison\vps_2026_06_02_strategy_regime_comparison.json --data-source autobot_state_db --data-path data\vps_autobot_state_2026-06-01.db --symbols BTCZEUR,ETHZEUR,SOLEUR,LTCZEUR,XLMZEUR,XRPZEUR,TRXEUR,ADAEUR,LINKEUR,DOTEUR,BCHEUR,ATOMEUR,AVAXEUR,AAVEEUR --output-dir reports\research\vps_2026_06_02_strategy_regime_baselines --include-regime-context --initial-capital-eur 1000 --order-notional-eur 100 --fee-bps 16 --spread-bps 8 --slippage-bps 4
```

Result:

```text
PASS - 11 buckets generated.
```

## Findings

- No strategy/regime bucket beats its best baseline.
- `trend_momentum / chaos` is positive vs no-trade but loses to regime buy-and-hold by `-251.259515 EUR`.
- `mean_reversion / high_vol` is positive vs no-trade but loses to regime buy-and-hold by `-338.103831 EUR`.
- `dynamic_grid / chaos` loses to random same-frequency by `-180.634537 EUR`.

## Risks / Warnings

- Baselines are simple diagnostics, not a complete statistical benchmark suite.
- `buy_and_hold_regime_segments` can be dominated by a small number of strong regime segments, so it should be interpreted as a guardrail, not as a trading recommendation.
- This does not replace walk-forward validation.

## Recommendation

Proceed to walk-forward strategy x regime validation with baselines before changing official paper behavior.
