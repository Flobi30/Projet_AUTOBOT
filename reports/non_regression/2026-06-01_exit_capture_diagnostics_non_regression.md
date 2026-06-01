# Non-Regression - Exit Capture Diagnostics

Date: 2026-06-01
Verdict: PASS

## Scope

This change adds research-only exit-capture diagnostics to AUTOBOT's replay and
loss-attribution stack. It measures how much favorable movement is captured or
given back before exit.

## Files Changed

| File | Change | Risk |
| --- | --- | --- |
| `src/autobot/v2/research/backtest_engine.py` | Adds `positive_exit_capture_bps`, `mfe_giveback_bps`, `mfe_capture_ratio`, and `positive_mfe_capture_ratio` to `TradeRecord.metadata.path`. | Low; research metadata only. |
| `src/autobot/v2/research/loss_attribution.py` | Aggregates exit capture, MFE giveback, positive MFE capture ratio and MFE-above-cost lost trade counts. | Low; report-only analytics. |
| `tests/research/test_backtest_engine.py` | Covers new path fields. | Low. |
| `tests/research/test_loss_attribution.py` | Covers aggregate exit-capture diagnostics. | Low. |
| `reports/research/vps_exit_capture_diagnostics_2026_06_01_summary.md` | Permanent summary of 14-symbol exit-capture matrix. | Documentation/report only. |

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
- The new fields are post-trade research diagnostics only.

## Commands Run

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\backtest_engine.py src\autobot\v2\research\loss_attribution.py tests\research\test_backtest_engine.py tests\research\test_loss_attribution.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_backtest_engine.py tests\research\test_loss_attribution.py tests\research\test_validation_matrix.py -q
```

Result: `12 passed in 0.28s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: `44 passed in 0.30s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: `24 passed in 0.18s`

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## Full Matrix Evidence

Command:

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m autobot.v2.research.validation_matrix --run-id vps_2026_06_01_top14_exit_capture --data-source autobot_state_db --data-path data\vps_autobot_state_2026-06-01.db --symbols TRXEUR,SOLEUR,ETHZEUR,BTCZEUR,LTCZEUR,XLMZEUR,XRPZEUR,ADAEUR,LINKEUR,DOTEUR,BCHEUR,ATOMEUR,AVAXEUR,AAVEEUR --strategies grid,trend,mean_reversion --output-dir reports\research_matrix\vps_2026_06_01_top14_exit_capture --min-closed-trades 30 --min-profit-factor 1.2 --max-drawdown-pct 15 --write-registry-recommendations --write-loss-attribution
```

Result:

- Cells: `42`
- Errors: `0`
- Closed trades: `1,318`
- Gross PnL: `-237.923673`
- Net PnL: `-659.683673`
- Total modeled cost: `632.640000`
- MFE-above-cost trades: `298`
- MFE-above-cost lost trades: `49`
- Average exit capture: `-18.035640 bps`
- Average MFE giveback: `52.108666 bps`
- Average positive MFE capture ratio: `0.452270`

The temporary full matrix output directory was removed after extracting the
permanent summary.

## Runtime/VPS

This was a local read-only replay from the copied VPS database. The VPS Docker
runtime was not modified or restarted.

## Risks Remaining

- Capture diagnostics use replay bar high/low, not full depth-aware tick path.
- The diagnostics explain exit behavior but do not yet change strategy exits.
- `average_mfe_capture_ratio` can be noisy when MFE is tiny; human reports
  should prefer positive capture ratio, MFE giveback and MFE-above-cost lost
  counts.

## Recommendation

Proceed to a research-only trend exit experiment. Trend has enough favorable
movement in some trades but captures too little of it before exit.
