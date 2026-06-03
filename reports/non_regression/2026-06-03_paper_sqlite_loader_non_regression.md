# Non-Regression - Paper SQLite Loader - 2026-06-03

Verdict: PASS

## Scope

This change connects the daily paper reporting path to AUTOBOT SQLite ledgers in
read-only mode.

Added capabilities:

- Load official closed paper trades from `autobot_state.db` / `trade_ledger`.
- Pair opening and closing legs by `position_id`.
- Treat closing `realized_pnl` as official net PnL.
- Reconstruct gross PnL as net PnL plus fees and estimated slippage.
- Load `decision_ledger` rows into `PaperDecisionRecord`.
- Load legacy `paper_trades.db` fills with FIFO matching as a fallback source.
- Extend `python -m autobot.v2.cli paper` with:
  - `--state-db`
  - `--paper-trades-db`
  - existing `--journal-path`

## Files Changed

- `src/autobot/v2/paper/ledger_loader.py`
  - New read-only SQLite loader.
  - Opens databases via `file:<path>?mode=ro`.
  - Converts runtime ledgers to `TradeJournal` and `PaperDecisionRecord`.

- `src/autobot/v2/paper/__init__.py`
  - Exposes loader APIs.

- `src/autobot/v2/cli.py`
  - `paper` command now accepts exactly one source:
    `--journal-path`, `--state-db`, or `--paper-trades-db`.

- `tests/paper/test_paper_ledger_loader.py`
  - Verifies `trade_ledger` pair reconstruction.
  - Verifies `decision_ledger` conversion.
  - Verifies missing opening-leg warning.
  - Verifies legacy `paper_trades.db` FIFO matching.

- `tests/test_v2_cli.py`
  - Adds CLI coverage for `--state-db`.

## What Must Not Have Changed

- Dashboard: unchanged.
- Runtime paper executor: unchanged.
- Kraken/live execution: unchanged.
- Strategy router: unchanged.
- Risk thresholds and sizing: unchanged.
- Existing APIs: unchanged.
- Docker/VPS behavior: unchanged.
- Persistent DB writes: unchanged.

## Trading Safety

- Loader is read-only and does not write to SQLite.
- No orders are created.
- No strategy registry mutation is performed.
- No live trading permission is granted.
- `paper_trades.db` FIFO fallback is labeled separately from official
  `trade_ledger` evidence.
- Missing opening legs are not silently hidden; they are surfaced as warnings.

## Validation

Commands executed:

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m py_compile src\autobot\v2\paper\ledger_loader.py src\autobot\v2\paper\__init__.py src\autobot\v2\cli.py tests\paper\test_paper_ledger_loader.py tests\test_v2_cli.py
```

Result: PASS

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\paper\test_paper_ledger_loader.py tests\paper\test_paper_trading_engine.py tests\test_v2_cli.py -q
```

Result: `15 passed in 0.27s`

```powershell
$env:PYTHONPATH='.codex_python_deps;src'; & 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m pytest tests\research tests\risk tests\paper tests\test_v2_cli.py -q
```

Result: `102 passed in 0.69s`

```powershell
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe' -m compileall -q src
```

Result: PASS

## Risks Remaining

- The official `trade_ledger` does not store a strategy column. The loader
  infers strategy from linked `decision_ledger` rows when available and falls
  back to `unknown`.
- `paper_trades.db` remains a legacy fill ledger, so FIFO reconstruction is a
  fallback, not the preferred source of truth.
- Spread cost is unavailable in current runtime ledgers and is recorded as
  zero; fees and slippage estimates are still separated.

## Recommendation

Next roadmap step: add a one-command research matrix CLI wrapper or a compact
daily paper report automation that reads `data/autobot_state.db` directly on the
VPS without changing the running bot.
