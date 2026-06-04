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

The audit reports observed notional, fees, adverse slippage, favorable
slippage, total cost bps, expected research cost bps and warnings when a source
is missing, materially cheaper/more expensive than the research baseline, or
contains abnormal signed slippage rows.

## Files Changed

- `src/autobot/v2/research/cost_parity_audit.py`
  - New read-only audit module.
  - Opens SQLite sources in read-only mode.
  - Counts only adverse signed `slippage_bps` as cost.
  - Tracks favorable slippage and slippage anomalies separately.
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
    handling, signed slippage handling, anomaly warning generation and report
    writing.
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
5 passed in 0.37s
```

Broader research/paper/CLI tests:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/research tests/paper tests/test_v2_cli.py tests/test_shadow_cost_bridge.py -q
```

Result:

```text
118 passed in 1.51s
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

## Local Snapshot Cost-Parity Evidence

Command:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli cost-parity `
  --run-id vps_2026_06_04_cost_parity_local_snapshot `
  --state-db data/vps_autobot_state_2026-06-04_2026-06-04_121159.db `
  --setup-shadow-db data/setup_shadow_lab.db `
  --output-dir reports/research/vps_2026_06_04_cost_parity
```

Result:

- official paper ledger status: `ok`;
- official paper cost rows: `1142`;
- official paper trade/position count: `599`;
- official paper average fee: `17.54 bps`;
- official paper average adverse slippage: `7.53 bps`;
- official paper average total cost: `25.08 bps`;
- research expected per-side cost: `25.00 bps`;
- cost delta: `+0.08 bps`;
- slippage anomaly rows: `24`;
- max absolute signed slippage: `294822.29 bps`;
- trend and mean-reversion shadow DBs were not configured in the local snapshot;
- setup shadow DB had no closed cost rows.

Generated reports:

- `reports/research/vps_2026_06_04_cost_parity/vps_2026_06_04_cost_parity_local_snapshot.json`
- `reports/research/vps_2026_06_04_cost_parity/vps_2026_06_04_cost_parity_local_snapshot.md`

## Risks Remaining

- Shadow trade tables collapse fees/spread/slippage into legacy buckets, so the
  audit warns with `shadow_cost_components_collapsed`.
- Official paper history contains signed slippage anomalies. They are now
  counted separately, but they still need a quality policy before using raw
  historical slippage as training evidence.
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
