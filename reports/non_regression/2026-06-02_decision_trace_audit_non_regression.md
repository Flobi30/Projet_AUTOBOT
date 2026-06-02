# Non-Regression - Decision Trace Audit

## Verdict

PASS_WITH_WARNINGS

## Scope

Added an isolated research diagnostic for canonical decision trace coverage.

Changed files:

- `src/autobot/v2/research/decision_trace_audit.py`
- `src/autobot/v2/research/__init__.py`
- `tests/research/test_decision_trace_audit.py`
- `reports/research/vps_2026_06_02_decision_trace_audit/vps_2026_06_02_decision_trace_audit.md`
- `reports/research/vps_2026_06_02_decision_trace_audit/vps_2026_06_02_decision_trace_audit.json`
- `reports/research/vps_decision_trace_audit_2026_06_02_summary.md`
- `reports/non_regression/2026-06-02_decision_trace_audit_non_regression.md`

## What Changed

- Added read-only SQLite audit of `decision_ledger`, `orders`, `trade_ledger`, and `signal_outcomes`.
- Reconstructs traces using shared identifiers: `decision_id`, `signal_id`, `client_order_id`, `exchange_order_id`, `position_id`, `event_id`, `trade_id`, `outcome_id`.
- Reports missing canonical stages for rejected and execution paths.
- Limits stored trace details to a configurable sample while keeping summary metrics computed over all traces.
- Added public lazy exports from `autobot.v2.research`.

## What Did Not Change

- No live trading logic changed.
- No paper executor changed.
- No order routing changed.
- No Kraken integration changed.
- No risk thresholds changed.
- No strategy router or promotion gate changed.
- No dashboard endpoint or frontend page changed.
- No Docker/VPS runtime was restarted or modified by this patch.

## Trading Safety

- No strategy promotion was added.
- No fallback permissive behavior was added.
- No order can be sent by this audit; it is read-only and research-only.
- The audit result must not be used as live readiness evidence.

## Tests

Commands executed:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\research\decision_trace_audit.py src\autobot\v2\research\__init__.py tests\research\test_decision_trace_audit.py
```

Result: PASS.

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research\test_decision_trace_audit.py -q
```

Result: 5 passed.

```powershell
$env:PYTHONPATH='src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research -q
```

Result: 65 passed.

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS.

```powershell
git diff --check
```

Result: PASS with Windows LF/CRLF warning for `src/autobot/v2/research/__init__.py`.

## Warning

The broader local check:

```powershell
$env:PYTHONPATH='src'; & '...\python3.12.exe' -m pytest tests\research\test_decision_trace_audit.py tests\test_decision_ledger.py tests\test_decision_learning.py -q
```

did not collect `tests/test_decision_ledger.py` or `tests/test_decision_learning.py` because this local Python environment is missing `fastapi`.

This is an environment dependency warning, not evidence of a code regression in the new research module.

## Runtime VPS

The VPS runtime was not changed or restarted by this patch. This patch only reads the local exported SQLite snapshot `data/vps_autobot_state_2026-06-01.db`.

## Evidence From VPS Snapshot

- Canonical complete traces: 455 / 8,948.
- Execution complete traces: 0 / 5,699.
- Main issue detected: orders/trades do not consistently link back to the canonical `decision_ledger` decision rows.
- Report: `reports/research/vps_decision_trace_audit_2026_06_02_summary.md`.

## Recommendation

Safe to proceed to the next roadmap step, with warning:

Before relying on paper PnL attribution for strategy promotion, implement the canonical execution trace bridge so every completed paper trade can be reconstructed from signal to realized PnL.
