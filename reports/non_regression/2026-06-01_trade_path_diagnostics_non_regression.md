# Non-Regression - Trade Path Diagnostics

Date: 2026-06-01
Verdict: PASS

## Scope

This change adds research-only trade path diagnostics to AUTOBOT's validation
stack. It does not alter runtime paper execution, strategy routing, risk
management, dashboard APIs, Docker, Kraken integration, or live trading.

## Files Changed

| File | Change | Risk |
| --- | --- | --- |
| `src/autobot/v2/research/backtest_engine.py` | Tracks post-entry high/low path for open research positions and writes MFE/MAE/cost-distance fields into `TradeRecord.metadata.path`. | Medium; replay accounting must avoid entry-bar look-ahead. |
| `src/autobot/v2/research/loss_attribution.py` | Aggregates average MFE, average MAE, MFE/cost ratio and MFE-above-cost counts. | Low; report-only analytics. |
| `tests/research/test_backtest_engine.py` | Adds coverage proving entry-bar high/low is not used in path diagnostics. | Low. |
| `tests/research/test_loss_attribution.py` | Adds coverage for path diagnostic aggregation and report rendering. | Low. |
| `reports/research/autobot_performance_audit_for_gpt55_2026-06-01.md` | Adds a copy-paste performance audit brief with latest VPS matrix/loss-attribution evidence. | Documentation only. |

## What Must Not Have Changed

| Area | Status |
| --- | --- |
| Dashboard | Not touched. |
| Runtime paper trading | Not touched. |
| Live trading | Not touched; no live flag or Kraken order path changed. |
| Strategy router | Not touched. |
| Risk management | Not touched. |
| Existing APIs | Not touched. |
| Docker/VPS runtime | Not touched. |
| Persistent data | Not touched. |
| Strategy signal logic | Not touched. |

## Trading Safety

- No live trading code path was modified.
- No strategy status, promotion rule, or registry gate was loosened.
- No sizing, leverage, cost guard, risk guard, or execution behavior was changed.
- New MFE/MAE fields are post-trade research metadata only.
- The entry bar's high/low is intentionally excluded when a position is opened,
  avoiding an obvious look-ahead diagnostic artifact.

## Commands Run

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\backtest_engine.py src\autobot\v2\research\loss_attribution.py tests\research\test_backtest_engine.py tests\research\test_loss_attribution.py
```

Result: PASS

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_backtest_engine.py tests\research\test_loss_attribution.py -q
```

Result: `9 passed in 0.17s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: `44 passed in 0.28s`

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_research_validation_harness.py tests\test_strategy_validation_registry.py -q
```

Result: `24 passed in 0.17s`

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## Real-Data Smoke

Command:

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m autobot.v2.research.validation_matrix --run-id smoke_trade_path_diagnostics --data-source autobot_state_db --data-path data\vps_autobot_state_2026-06-01.db --symbols TRXEUR --strategies grid --output-dir reports\research_matrix\smoke_trade_path_diagnostics --min-closed-trades 1 --write-loss-attribution
```

Result:

- Cell count: `1`
- Errors: `0`
- Symbol/strategy: `TRXEUR / grid`
- Closed trades: `6`
- Net PnL: `-6.764075`
- Profit factor: `0.097923`
- Average MFE: `33.403325 bps`
- Average MAE: `-115.218855 bps`
- MFE-above-cost trades: `1`
- Decision: `reject`

The temporary smoke output directory was removed after extracting the evidence.

## Risks Remaining

- MFE/MAE is now available for research journals, but the full 14-symbol matrix
  has not yet been rerun with the new diagnostics committed into a permanent
  summary.
- The diagnostics use OHLCV bar high/low, not tick-by-tick or depth-aware path.
- These fields explain trade path quality, but do not by themselves fix entry,
  exit or routing logic.

## Recommendation

Continue to the next roadmap step: rerun the 14-symbol strategy matrix with the
new path diagnostics and summarize whether losses are driven mainly by weak
entries, poor exits, target/cost mismatch, or adverse regime behavior.
