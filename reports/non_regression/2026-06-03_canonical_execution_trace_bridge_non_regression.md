# Non-Regression Report - Canonical Execution Trace Bridge

Date: 2026-06-03
Scope: signal/decision trace persistence before paper order and trade ledger writes.
Verdict: PASS_WITH_WARNINGS

## Summary

This change tightens trace ordering in `SignalHandlerAsync` so accepted BUY/SELL decisions are persisted before downstream order creation and trade ledger writes. It does not change trading thresholds, sizing rules, risk guards, live mode, Kraken order behavior, or dashboard contracts.

The expected impact is forward-looking only: future accepted paper decisions should be easier to reconstruct as a canonical chain:

`signal_received -> buy_accepted/sell_accepted -> order -> trade ledger`

Existing historical traces are not retroactively repaired.

## Files Changed

- `.gitignore`
  - Adds `.codex_python_deps/` to keep local Codex test dependencies out of Git.

- `src/autobot/v2/signal_handler_async.py`
  - Adds an optional `persist_async` parameter to `_record_runtime_event`.
  - Adds `_record_and_persist_runtime_event`, which records a runtime event and awaits persistence before continuing.
  - Uses synchronous best-effort persistence for:
    - `signal_received`
    - `buy_accepted`
    - `sell_accepted`

- `tests/test_signal_handler_async_unit.py`
  - Adds persistence and order-state fakes to prove accepted decisions are written before order creation.
  - Adds BUY and SELL canonical trace tests.
  - Keeps existing paper sizing and sell PnL tests intact.

## Logic Changed

Only event persistence ordering changed for the critical trace path.

Unchanged:

- Cost guard thresholds.
- ATR/microstructure logic.
- Opportunity scoring.
- Position sizing.
- Leverage.
- Risk management.
- Kill switch behavior.
- Paper/live mode boundaries.
- Kraken live order activation.
- Dashboard API shape.

Persistence remains best-effort because `_persist_runtime_event` already catches persistence exceptions. A DB write failure should not silently authorize a live path or change trade eligibility.

## Trading Safety

Confirmed:

- No live trading flag was enabled.
- No new path sends real Kraken orders.
- No strategy promotion or live gate was changed.
- No fallback permissive router was added.
- No sizing/risk/execution threshold was loosened.
- Learning/candidate/shadow-only strategies remain subject to the existing promotion gate.

## Validation Commands

Compile touched files:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\signal_handler_async.py tests\test_signal_handler_async_unit.py
```

Result: PASS

Focused signal-handler tests:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_signal_handler_async_unit.py -q
```

Result: 21 passed

Research validation tests:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: 65 passed

Compile all backend source:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

Broader related decision/ledger tests:

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_signal_handler_async_unit.py tests\test_decision_ledger.py tests\test_decision_learning.py -q
```

Result: 28 passed, 1 warning

Warning:

- `StarletteDeprecationWarning` from `.codex_python_deps\fastapi\testclient.py`, related to local test dependency compatibility. It is not caused by this patch and does not affect the touched signal/ledger path.

## Runtime VPS

The VPS/container was not restarted as part of this patch. Runtime behavior was not changed on the server yet.

Recommended follow-up after deployment:

1. Restart/redeploy normally.
2. Check `/health`.
3. Check container logs for persistence errors.
4. Let AUTOBOT produce fresh paper decisions.
5. Re-run the decision trace audit on a fresh VPS snapshot and compare canonical trace completeness against the previous baseline:
   - 8,948 reconstructed traces.
   - 455 complete traces.
   - 0 execution-complete traces.
   - 0 closing trade rows with decision IDs.

## Residual Risks

- This patch improves event ordering for future accepted BUY/SELL decisions, but does not retroactively fix old ledger rows.
- If persistence fails internally, the current handler logs/catches errors rather than blocking the trade path. This preserves existing runtime behavior, but still means a severe DB issue can produce incomplete trace records.
- Closing PnL lineage may still need a second bridge if exit rows cannot be linked back to the original opening decision/strategy after fresh runtime validation.

## Recommendation

Proceed to the next roadmap step only after this patch is deployed and a fresh trace audit confirms improvement. If canonical completeness remains low, focus next on linking close events and realized PnL rows back to their opening decision and strategy lineage.
