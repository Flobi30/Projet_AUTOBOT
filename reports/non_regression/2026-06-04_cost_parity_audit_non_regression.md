# Non-Regression Report - Cost Parity Audit

Verdict: PASS

Date: 2026-06-04

## Change Summary

This change adds a read-only research audit that compares observed execution
costs across:

- official paper `trade_ledger`;
- trend shadow closed trades;
- mean reversion shadow closed trades;
- setup shadow closed trades;
- research `ExecutionCostModel` assumptions.

The audit reports observed notional, fees, slippage, total cost bps, expected
research cost bps and warnings when a source is missing or materially cheaper
or more expensive than the research baseline.

## Files Changed

- `src/autobot/v2/research/cost_parity_audit.py`
  - New read-only audit module.
  - Opens SQLite sources in read-only mode.
  - Produces JSON/Markdown reports.
  - Does not mutate ledgers, runtime state, strategy registry, router, sizing,
    risk or execution.
- `src/autobot/v2/cli.py`
  - Adds `cost-parity` CLI command.
  - Prints JSON and optionally writes reports.
  - Keeps explicit safety notes.
- `src/autobot/v2/research/__init__.py`
  - Exposes lazy research exports for the audit module.
- `tests/research/test_cost_parity_audit.py`
  - Covers paper ledger cost extraction, shadow cost extraction, missing DB
    handling, warning generation and report writing.
- `tests/test_v2_cli.py`
  - Adds CLI smoke coverage for `cost-parity`.
- `docs/research/CLI_WORKFLOWS.md`
  - Documents the repeatable cost parity workflow.

## What Must Not Have Changed

- Dashboard: unchanged.
- Paper trading runtime: unchanged.
- Live trading safety: unchanged.
- Strategy router: unchanged.
- Risk management: unchanged.
- Existing APIs/endpoints: unchanged.
- Docker/VPS behavior: unchanged.
- Configuration and persistent data: unchanged.

## Trading Safety

- No strategy can be promoted by this audit.
- No order can be created by this audit.
- No live trading permission is granted.
- No registry mutation is performed.
- No fallback permissive path was added.
- No sizing, leverage, risk, cost guard or execution threshold was changed.

## Validation Evidence

Targeted tests:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/research/test_cost_parity_audit.py tests/test_v2_cli.py::test_cli_cost_parity_audits_read_only_cost_sources -q
```

Result:

```text
4 passed in 0.37s
```

Broader research/paper/CLI tests:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/research tests/paper tests/test_v2_cli.py tests/test_shadow_cost_bridge.py -q
```

Result:

```text
117 passed in 1.28s
```

Python syntax validation:

```powershell
python -m compileall -q src
```

Result: PASS.

Diff whitespace check:

```powershell
git diff --check
```

Result: PASS. Git reported only existing CRLF conversion warnings for touched
text files.

## Runtime VPS Check

Command:

```powershell
curl.exe -sS --max-time 15 http://204.168.251.201:8080/health
```

Result:

```json
{
  "status": "healthy",
  "version": "2.0.0",
  "components": {
    "orchestrator": "running",
    "websocket": "connected",
    "instances": 14
  }
}
```

No container restart was performed for this local research-only change.

## Risks Remaining

- Shadow trade tables collapse fees/spread/slippage into legacy buckets, so the
  audit warns with `shadow_cost_components_collapsed`.
- Historical shadow rows created before the shadow cost bridge may still show
  cheaper costs than the current research baseline; the audit will flag that
  instead of rewriting history.
- The audit does not yet load legacy `paper_trades.db`; it focuses on the
  official paper `trade_ledger` and shadow lab DBs.

## Recommendation

Proceed to run `cost-parity` on fresh VPS-copied SQLite databases, then use its
warnings to decide whether the next roadmap step should be:

1. official paper ledger cost unification;
2. shadow history annotation/backfill policy;
3. central TradeJournal adoption for runtime evidence.

