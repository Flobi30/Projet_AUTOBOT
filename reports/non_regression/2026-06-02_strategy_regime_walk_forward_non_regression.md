# Non-Regression Report - Strategy Regime Walk-Forward - 2026-06-02

## Verdict

PASS_WITH_WARNINGS

The change is research-only and did not modify paper execution, live execution, strategy routing, risk sizing, Docker, Kraken integration, dashboard, or persistent runtime state. Warning: VPS runtime endpoints were not rechecked because this change has not been deployed or restarted on the VPS in this step.

## What Changed

| File | Change | Risk |
| --- | --- | --- |
| `src/autobot/v2/research/strategy_regime_walk_forward.py` | Added chronological strategy/regime walk-forward diagnostics with baseline comparison and sample-size guard. | Low, isolated to research validation. |
| `src/autobot/v2/research/validation_matrix.py` | Added `--write-strategy-regime-walk-forward` output option. | Low, opt-in CLI only. |
| `src/autobot/v2/research/__init__.py` | Exposed new research functions through lazy exports. | Low, import surface only. |
| `tests/research/test_strategy_regime_walk_forward.py` | Added unit coverage for fold counting, tiny-sample rejection, and report writing. | Test-only. |
| `tests/research/test_validation_matrix.py` | Added CLI assertion for the new opt-in report. | Test-only. |
| `reports/research/vps_2026_06_02_strategy_regime_walk_forward_defaults/*` | Permanent markdown and JSON artifacts from VPS-state replay. | Report-only. |
| `reports/research/vps_strategy_regime_walk_forward_2026_06_02_summary.md` | Human-readable interpretation of the diagnostic. | Report-only. |

## What Did Not Change

| Area | Confirmation |
| --- | --- |
| Dashboard | Not touched. |
| Paper trading runtime | Not touched. |
| Live trading | Not touched and not enabled. |
| Strategy router | Not touched. |
| Risk management | Not touched. |
| Execution engine | Not touched. |
| Kraken integration | Not touched. |
| Docker/VPS configuration | Not touched. |
| Persistent databases | Read-only use of `data/vps_autobot_state_2026-06-01.db`; no mutation. |
| Strategy promotion | No automatic promotion, no registry mutation. |

## Trading Safety

- No strategy can pass live because this module has no live execution path.
- No real order can be sent because the change only reads research journals and market bars.
- `candidate`, `learning`, `shadow`, or `paper` status handling is not relaxed.
- The report explicitly states that it is research-only and does not authorize paper or live execution.
- The new sample-size guard prevents tiny positive buckets from being labelled as validated.

## Validation Commands

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_strategy_regime_walk_forward.py tests\research\test_strategy_regime_baselines.py tests\research\test_validation_matrix.py -q
```

Result: `8 passed in 0.22s`.

```powershell
$env:PYTHONPATH='src'; $out = & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m autobot.v2.research.validation_matrix --run-id vps_2026_06_02_strategy_regime_wf_defaults --data-source autobot_state_db --data-path data\vps_autobot_state_2026-06-01.db --symbols BTCZEUR,ETHZEUR,SOLEUR,LTCZEUR,XLMZEUR,XRPZEUR,TRXEUR,ADAEUR,LINKEUR,DOTEUR,BCHEUR,ATOMEUR,AVAXEUR,AAVEEUR --strategies grid,trend,mean_reversion --output-dir reports\research_matrix\vps_2026_06_02_strategy_regime_wf_defaults --include-regime-context --train-window-bars 600 --test-window-bars 30 --step-window-bars 30 --min-folds 2 --min-passing-folds 2 --fee-bps 16 --spread-bps 8 --slippage-bps 4 --write-strategy-regime-walk-forward; $out[-40..-1]
```

Result: `success_count 42`; `fold_count 1696`; `evaluated_bucket_count 1057`.

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\strategy_regime_walk_forward.py src\autobot\v2\research\validation_matrix.py src\autobot\v2\research\__init__.py tests\research\test_strategy_regime_walk_forward.py tests\research\test_validation_matrix.py
```

Result: PASS.

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: `60 passed in 0.38s`.

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS.

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: `24 passed in 0.18s`.

## Runtime VPS

Not rechecked in this step. This code is local research/reporting only and no Docker rebuild, VPS restart, or runtime deploy was performed.

## Performance Finding

The walk-forward run does not validate any current strategy/regime bucket for promotion.

| Key Bucket | Finding |
| --- | --- |
| `dynamic_grid / chaos` | 308 trades, net `-125.063335` EUR, delta vs best baseline `-353.924994` EUR. |
| `mean_reversion / chaos` | 494 trades, net `-240.891029` EUR, delta vs best baseline `-347.327016` EUR. |
| `trend_momentum / chaos` | 203 trades, net `-101.778844` EUR, delta vs best baseline `-125.826026` EUR. |
| `mean_reversion / high_vol` | Positive `+0.714304` EUR, but only 4 trades total. It remains `keep_testing` due to insufficient sample size. |

## Risks Remaining

- The walk-forward diagnostic evaluates trade journals produced by existing validation runs; it does not yet replay every live/paper runtime decision from a single official ledger.
- The baseline comparison is conservative but still simplified compared with full order-book replay.
- The VPS runtime was not rechecked because no deploy/restart happened.

## Recommendation

Proceed to the next research-validation step only after commit/push. Do not promote any strategy based on this run. The next useful step is to connect this diagnostic to the future unified decision ledger so rejected, accepted, and closed paper decisions can be compared with the same chronology.
