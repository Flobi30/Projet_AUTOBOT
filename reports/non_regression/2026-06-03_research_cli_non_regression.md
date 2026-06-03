# Non-Regression - Research CLI - 2026-06-03

Verdict: PASS

## Scope

This change adds a unified research/paper-report CLI at `src/autobot/v2/cli.py`.

Commands added:

- `audit`: read-only status for `docs/AUTOBOT_AUDIT_REPORT.md`.
- `backtest`: wrapper around the existing isolated research `ValidationRunner`.
- `walk-forward`: wrapper around the existing isolated walk-forward path.
- `paper`: builds a daily paper report from a research `TradeJournal` JSON.
- `leaderboard`: builds a research-only strategy scorecard from a validation matrix JSON.

## Files Changed

- `src/autobot/v2/cli.py`
  - New orchestration CLI for existing research/paper modules.
  - Emits JSON output for automation.
  - Does not start orchestrator/runtime services.
  - Does not mutate the strategy registry.
  - Does not submit or prepare Kraken orders.

- `tests/test_v2_cli.py`
  - Covers `audit`, `backtest`, `walk-forward`, `paper`, and `leaderboard`.
  - Confirms live promotion remains false in validation outputs.
  - Confirms scorecard/leaderboard does not grant live permission.

## What Must Not Have Changed

- Dashboard: unchanged.
- Runtime paper executor: unchanged.
- Kraken/live execution: unchanged.
- Strategy router: unchanged.
- Risk sizing/risk thresholds: unchanged.
- Existing APIs: unchanged.
- Docker/VPS behavior: unchanged.
- Persistent data: unchanged.

## Trading Safety

- No live trading flag was changed.
- No CLI command can submit a real order.
- `backtest` and `walk-forward` use isolated research validation only.
- `paper` summarizes a `TradeJournal`; it does not create orders.
- `leaderboard` writes scorecards only; it does not mutate `strategy_hypotheses.json`.
- All emitted strategy decisions keep `live_promotion_allowed=false`.

## Validation

Initial sandbox note:

- `py -3.12` and WindowsApps Python failed inside the sandbox because the local launcher was unavailable or access was denied.
- The same Python 3.12 commands were then run with approved escalation.

Commands executed:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\cli.py tests\test_v2_cli.py
```

Result: PASS

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\test_v2_cli.py -q
```

Result: `5 passed in 0.22s`

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research tests\risk tests\paper tests\test_v2_cli.py -q
```

Result: `98 passed in 0.72s`

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## Risks Remaining

- The `paper` command currently consumes a research `TradeJournal` JSON. It does not yet load official runtime paper ledgers directly from SQLite.
- The CLI does not yet provide a one-command matrix runner; the existing `validation_matrix.py` CLI remains available for that.
- No VPS runtime restart was performed because this is an isolated research CLI addition.

## Recommendation

Proceed to the next roadmap step: add read-only loaders from official paper ledgers into the paper daily reporting path, so daily paper reports can be generated from runtime data without manual journal conversion.
