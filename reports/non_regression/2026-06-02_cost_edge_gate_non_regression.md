# Non-Regression - Research Cost/Edge Gate - 2026-06-02

Verdict: `PASS_WITH_WARNINGS`

## Scope

This check covers the research-only cost-aware signal gate added to the deterministic backtest engine.

The gate is disabled by default. It only applies when `BacktestConfig.min_signal_net_edge_bps` is explicitly set.

## Files Changed

- `src/autobot/v2/research/backtest_engine.py`
  - Added `BacktestConfig.min_signal_net_edge_bps`.
  - Added a pre-execution gate for BUY signals:
    - reads `gross_edge_bps` from signal metadata;
    - estimates round-trip cost from the configured `ExecutionCostModel`;
    - rejects missing/invalid/weak edge when the gate is enabled;
    - records accepted edge context in trade journal metadata.

- `src/autobot/v2/research/validation_runner.py`
  - Exposes `min_signal_net_edge_bps` through runner config and CLI.

- `src/autobot/v2/research/validation_matrix.py`
  - Exposes `min_signal_net_edge_bps` through matrix config and CLI.

- `tests/research/test_backtest_engine.py`
  - Adds tests proving weak edge is rejected and accepted edge context is journaled.

- `reports/research/vps_trend_cost_edge_gate_experiment_2026_06_02_summary.md`
- `reports/research/vps_trend_cost_edge_gate_experiment_2026_06_02_summary.json`
  - Permanent research evidence from the local VPS-derived dataset.

## Modules Not Changed

- Runtime paper executor: not modified.
- Live/Kraken execution: not modified.
- Strategy router: not modified.
- Risk manager: not modified.
- Dashboard/API: not modified.
- Strategy registry promotion gates: not modified.
- Persistent VPS/runtime data: not modified.

## Trading Safety

- The gate is research-only and disabled by default.
- No order can be sent live from this path.
- Missing `gross_edge_bps` is rejected when the gate is enabled, avoiding permissive fallback behavior.
- The gate does not promote any strategy automatically.
- `live_promotion_allowed` remains false in tested paths.

## Validation Evidence

Commands run locally:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\backtest_engine.py src\autobot\v2\research\validation_runner.py src\autobot\v2\research\validation_matrix.py tests\research\test_backtest_engine.py
```

Result: pass.

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_backtest_engine.py tests\research\test_validation_runner.py tests\research\test_validation_matrix.py -q
```

Result: `14 passed in 0.23s`.

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: `51 passed in 0.28s`.

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: `24 passed in 0.17s`.

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: pass.

## Research Evidence

The gate was tested on the local VPS-derived 14-symbol dataset using the current best trend research entry filter:

- `confirm_bps=40`
- `min_momentum_bps=100`
- `min_atr_bps=15`

Results:

- No gate: `75` trades, `-27.351476` EUR net.
- Edge gate `80` bps: `47` trades, `-14.736634` EUR net.
- Edge gate `120` bps: `30` trades, `-6.372771` EUR net.

Conclusion:

- Cost-aware gating reduces losses and makes gross PnL positive at `120` bps.
- Net PnL remains negative after modeled fees/spread/slippage.
- No promotion is justified yet.

## Risks Remaining

- The best tested gate has only `30` trades, below a robust validation threshold.
- The dataset is runtime price samples, not a long historical multi-regime OHLCV set.
- Regime context remains incomplete in replay journals.
- The gate estimates round-trip cost conservatively from signal metadata; richer bid/ask/order-book data would improve realism.

## Next Recommended Action

Keep the gate as research infrastructure and run combined replay experiments:

- `strong_momentum + edge_120 + exit variants`;
- longer/more diverse historical datasets;
- regime-aware analysis before any paper promotion.
