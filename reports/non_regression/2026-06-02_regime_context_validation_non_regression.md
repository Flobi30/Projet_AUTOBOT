# Non Regression - Regime Context Validation - 2026-06-02

## Verdict

PASS_WITH_WARNINGS

## Scope

This change adds opt-in regime context enrichment to the isolated research validation pipeline.

It does not change runtime paper execution, live trading, Kraken integration, the dashboard, the production strategy router, sizing, leverage, or risk/execution rules.

## Files Changed

- `src/autobot/v2/research/regime_context.py`
  - New research-only helper to attach Markov/entropy regime context to `MarketBar.metadata`.
  - Enrichment is chronological per symbol and never uses future bars.

- `src/autobot/v2/research/validation_runner.py`
  - Adds `include_regime_context: bool = False`.
  - Adds CLI flag `--include-regime-context`.
  - Enriches bars only when explicitly requested.

- `src/autobot/v2/research/validation_matrix.py`
  - Propagates `include_regime_context`.
  - Adds CLI flag `--include-regime-context`.
  - Adds `--write-setup-quality` report generation.

- `src/autobot/v2/research/strategy_signal_generators.py`
  - Copies `regime`, `regime_context`, and `regime_source` from enriched bars into research signal metadata.

- `src/autobot/v2/research/setup_quality.py`
  - Adds multi-journal setup-quality aggregation for matrix outputs.

- `src/autobot/v2/research/__init__.py`
  - Exposes the new research helpers lazily.

- `tests/research/test_regime_context.py`
  - Verifies chronological/no-future regime enrichment and preservation of explicit regime labels.

- `tests/research/test_validation_runner.py`
  - Verifies the runner can write regime context into exported trade journals.

- `tests/research/test_validation_matrix.py`
  - Verifies matrix setup-quality report generation.

- `reports/research/vps_trend_regime_context_experiment_2026_06_02_summary.md`
- `reports/research/vps_trend_regime_context_experiment_2026_06_02_summary.json`
  - Permanent research summary for the first regime-labeled replay.

## What Must Not Have Changed

- Dashboard: not touched.
- Official paper trading: not touched.
- Live safety: not touched.
- Strategy router: not touched.
- Risk management: not touched.
- Kraken order/execution code: not touched.
- Persistent runtime DB schemas: not touched.
- Docker/VPS runtime behavior: not redeployed or changed.

## Trading Safety

- No live flag was enabled.
- No strategy registry promotion was performed.
- No candidate/learning strategy can bypass the existing promotion gate from this change.
- The enrichment is research-only and opt-in.
- `live_promotion_allowed` remains `False` in validation decisions.

## Validation Commands

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\regime_context.py src\autobot\v2\research\validation_runner.py src\autobot\v2\research\validation_matrix.py src\autobot\v2\research\strategy_signal_generators.py src\autobot\v2\research\setup_quality.py src\autobot\v2\research\__init__.py tests\research\test_regime_context.py tests\research\test_validation_runner.py tests\research\test_validation_matrix.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_regime_context.py tests\research\test_validation_runner.py tests\research\test_validation_matrix.py tests\research\test_setup_quality.py -q
```

Result: `11 passed in 0.22s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: `54 passed in 0.31s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: `24 passed in 0.17s`

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## Research Replay Evidence

Run: `vps_2026_06_02_trend_regime_context_edge_120`

Configuration:

- Strategy: `trend`
- `confirm_bps=40`
- `min_momentum_bps=100`
- `min_atr_bps=15`
- `min_signal_net_edge_bps=120`
- `include_regime_context=True`

Result:

- Matrix cells: `14`
- Success cells: `14`
- Errors: `0`
- Closed trades: `30`
- Gross PnL: `3.227229 EUR`
- Net PnL: `-6.372771 EUR`

By regime:

- `high_vol`: `6` trades, `0%` win rate, `-7.609117 EUR` net.
- `chaos`: `24` trades, `41.6667%` win rate, `+1.236346 EUR` net.

This proves regime context now reaches the research journal and setup-quality reports. It does not prove live readiness.

## Warnings

- The first regime-labeled replay is still a small sample (`30` closed trades).
- The result is still net negative overall.
- The `chaos` bucket is slightly positive but must not be trusted without longer replay, baselines, and walk-forward validation.
- VPS runtime endpoints were not checked because this change is not deployed and does not touch runtime code.

## Recommended Next Step

Use the same regime-labeled validation to compare:

- grid by regime;
- trend by regime with baselines;
- mean-reversion by regime.

Do not change official paper execution until a strategy beats no-trade, buy-and-hold, and random-entry baselines net of costs with enough closed trades.

