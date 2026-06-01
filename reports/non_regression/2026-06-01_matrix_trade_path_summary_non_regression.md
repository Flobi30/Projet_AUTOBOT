# Non-Regression - Matrix Trade Path Summary

Date: 2026-06-01
Verdict: PASS

## Scope

This change extends research-only matrix loss attribution with aggregate MFE/MAE
diagnostics and records a permanent VPS summary based on the 14-symbol replay.

## Files Changed

| File | Change | Risk |
| --- | --- | --- |
| `src/autobot/v2/research/loss_attribution.py` | Adds matrix-level aggregate MFE, MAE, MFE/cost ratio and MFE-above-cost counts to JSON and Markdown reports. | Low; report-only research analytics. |
| `tests/research/test_loss_attribution.py` | Covers weighted matrix MFE/MAE aggregation. | Low. |
| `reports/research/vps_trade_path_diagnostics_2026_06_01_summary.md` | Permanent summary of 14-symbol trade-path matrix. | Documentation/report only. |

## What Must Not Have Changed

| Area | Status |
| --- | --- |
| Dashboard | Not touched. |
| Runtime paper trading | Not touched. |
| Live trading | Not touched. |
| Strategy router | Not touched. |
| Risk management | Not touched. |
| Existing APIs | Not touched. |
| Docker/VPS runtime | Not touched. |
| Persistent data | Not touched. |
| Strategy signal logic | Not touched. |

## Trading Safety

- No live trading code path was modified.
- No Kraken order submission path was modified.
- No strategy status or registry gate was loosened.
- No sizing, leverage, cost guard, execution or risk rule was changed.
- The matrix output remains research-only and does not promote strategies.

## Commands Run

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\loss_attribution.py tests\research\test_loss_attribution.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_loss_attribution.py tests\research\test_validation_matrix.py -q
```

Result: `6 passed in 0.14s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: `44 passed in 0.25s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: `24 passed in 0.15s`

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## Full Matrix Evidence

Command:

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m autobot.v2.research.validation_matrix --run-id vps_2026_06_01_top14_trade_path --data-source autobot_state_db --data-path data\vps_autobot_state_2026-06-01.db --symbols TRXEUR,SOLEUR,ETHZEUR,BTCZEUR,LTCZEUR,XLMZEUR,XRPZEUR,ADAEUR,LINKEUR,DOTEUR,BCHEUR,ATOMEUR,AVAXEUR,AAVEEUR --strategies grid,trend,mean_reversion --output-dir reports\research_matrix\vps_2026_06_01_top14_trade_path --min-closed-trades 30 --min-profit-factor 1.2 --max-drawdown-pct 15 --write-registry-recommendations --write-loss-attribution
```

Result:

- Cells: `42`
- Errors: `0`
- Closed trades: `1,318`
- Gross PnL: `-237.923673`
- Net PnL: `-659.683673`
- Total modeled cost: `632.640000`
- Cost-flipped trades: `301`
- MFE-above-cost trades: `298`
- Average MFE: `34.073026 bps`
- Average MAE: `-54.518933 bps`
- Average MFE/Cost ratio: `0.681461`

The temporary full matrix output directory was removed after extracting the
permanent summary.

## Runtime/VPS

This was a local read-only replay from the copied VPS database. The VPS Docker
runtime was not modified or restarted.

## Risks Remaining

- The matrix uses `market_price_samples`, not full historical depth/tick data.
- MFE/MAE is derived from replay bars; it is not yet depth-aware.
- This confirms the problem shape but does not yet change strategy behavior.

## Recommendation

Proceed to exit-capture diagnostics, especially for `trend`, because it often
has enough favorable movement to cover costs but still exits net negative.
