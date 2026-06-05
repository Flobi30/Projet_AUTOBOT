# Non-Regression - Standard Audit Runner - 2026-06-05

Verdict: PASS_WITH_WARNINGS

## Scope

This change adds a repeatable read-only AUTOBOT validation bundle.

Changed files:

- `src/autobot/v2/research/standard_audit_runner.py`
- `src/autobot/v2/cli.py`
- `tests/test_v2_cli.py`
- `docs/research/CLI_WORKFLOWS.md`

New CLI command:

```powershell
python -m autobot.v2.cli standard-audit --run-id <run_id> --state-db <state.db>
```

The command orchestrates existing evidence layers:

- canonical dataset build from state DB;
- research validation matrix;
- standard research reports;
- official paper ledger daily report;
- paper vs research comparison;
- decision trace audit;
- cost parity audit;
- PnL causality snapshot.

## What Did Not Change

- No dashboard route or React page changed.
- No paper runtime order path changed.
- No Kraken live execution path changed.
- No strategy router runtime behavior changed.
- No risk manager, sizing, leverage, stop-loss or take-profit rule changed.
- No Docker or VPS configuration changed.
- No persistent strategy registry mutation was added.

## Trading Safety

Confirmed from code inspection and smoke output:

- The runner is read-only.
- It does not start AUTOBOT runtime services.
- It does not submit paper or live orders.
- It does not mutate `docs/research/strategy_hypotheses.json`.
- It does not authorize live trading.
- The CLI output includes `No live trading permission is granted.`

The 14 runtime instances visible in `/health` are not touched by this command and do not bypass the promotion gate.

## Tests

Targeted test:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_v2_cli.py::test_cli_standard_audit_runs_full_read_only_bundle -q
```

Result:

```text
1 passed in 0.21s
```

Research/paper regression block:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_v2_cli.py tests/paper tests/research tests/test_pnl_causality_audit.py tests/test_shadow_cost_bridge.py -q
```

Result:

```text
124 passed in 1.57s
```

Syntax validation:

```powershell
python -m compileall -q src
```

Result: PASS.

Note: `compileall` regenerated tracked `.pyc` files; they were restored before commit.

## Real Snapshot Smoke

Command:

```powershell
$env:PYTHONPATH='src'
python -m autobot.v2.cli standard-audit `
  --run-id vps_2026_06_05_standard_audit_trx_smoke `
  --state-db data/vps_autobot_state_2026-06-04_2026-06-04_121159.db `
  --symbols TRXEUR `
  --strategies grid `
  --timeframe 5m `
  --output-dir reports/research/vps_2026_06_05_standard_audit_trx_smoke `
  --dataset-output-dir data/research/vps_2026_06_05_standard_audit_trx_smoke `
  --include-regime-context `
  --min-closed-trades 1 `
  --train-window-bars 20 `
  --test-window-bars 10 `
  --step-window-bars 10 `
  --min-folds 1 `
  --min-passing-folds 1 `
  --decision-trace-sample-limit 20
```

Summary:

```json
{
  "dataset_usable_samples": 6841,
  "dataset_bars": 1975,
  "matrix_cells": 1,
  "matrix_success": 1,
  "paper_loader_trades": 455,
  "paper_daily_trades": 10,
  "paper_vs_research_buckets": 16,
  "paper_vs_research_divergent": 15,
  "decision_trace_count": 8959,
  "decision_trace_sample_count": 20,
  "pnl_closed_trades": 455,
  "pnl_net": -21.397803,
  "safety_has_no_live": true
}
```

Warnings from smoke:

- `slippage_bps_anomalies`
- `trend_shadow_not_configured`
- `mean_reversion_shadow_not_configured`
- `setup_shadow_not_configured`

These warnings are existing evidence gaps/anomalies surfaced by the audit, not new runtime behavior.

## VPS Runtime Check

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

Warning: Docker log inspection was not part of this local runner validation. Public `/health` is healthy, but this report does not claim a full VPS log audit.

## Risk Assessment

Risk level: low.

Reasoning:

- The new code composes existing read-only reporting modules.
- The CLI does not import or call Kraken order submission.
- The smoke output includes explicit no-live safety notes.
- Focused tests cover command wiring and artifact generation.

Residual risks:

- The standard bundle can surface large divergence counts, but it does not fix them.
- Shadow DB paths are optional; missing shadow sources are reported as warnings.
- Full VPS logs should still be checked during deployment windows.

## Recommendation

Proceed to the next roadmap step only as measurement/validation work:

1. keep using `standard-audit` as the default fresh VPS evidence command;
2. compare official paper vs research replay on fresh snapshots;
3. only change strategy execution after the audit explains where paper losses originate.

