# Non-Regression - Standard Audit Quick Mode - 2026-06-05

Verdict: PASS_WITH_WARNINGS

## Scope

This change adds a quick mode to `standard-audit`:

```powershell
python -m autobot.v2.cli standard-audit --skip-standard-reports ...
```

Changed files:

- `src/autobot/v2/research/standard_audit_runner.py`
- `src/autobot/v2/cli.py`
- `tests/test_v2_cli.py`
- `docs/research/CLI_WORKFLOWS.md`

The quick mode skips the expensive matrix annex reports while keeping:

- dataset build;
- validation matrix;
- official paper daily report;
- paper vs research comparison;
- decision trace audit;
- cost parity audit;
- PnL causality snapshot.

Default behavior is unchanged: standard reports remain enabled unless `--skip-standard-reports` is passed.

## What Did Not Change

- No runtime paper execution changed.
- No live execution changed.
- No strategy router behavior changed.
- No risk, sizing, leverage, stop-loss or take-profit changed.
- No dashboard files changed.
- No Docker/VPS configuration changed.
- No persistent DB or strategy registry mutation was added.

## Trading Safety

Confirmed:

- The command remains read-only.
- No paper or live order can be created.
- No live trading permission is granted.
- The smoke output retained `No live trading permission is granted.`

## Tests

Focused tests:

```powershell
$env:PYTHONPATH='src'
python -m pytest `
  tests/test_v2_cli.py::test_cli_standard_audit_runs_full_read_only_bundle `
  tests/test_v2_cli.py::test_cli_standard_audit_can_skip_matrix_annex_reports -q
```

Result:

```text
2 passed in 0.28s
```

Research/paper regression block:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_v2_cli.py tests/paper tests/research tests/test_pnl_causality_audit.py tests/test_shadow_cost_bridge.py -q
```

Result:

```text
127 passed in 1.65s
```

Syntax validation:

```powershell
python -m compileall -q src
```

Result: PASS.

Note: `compileall` regenerated tracked `.pyc` files; they were restored before commit.

## Real Snapshot Smoke

The full 14-symbol x 3-strategy audit exceeded 184 seconds before this change.
The 14-symbol grid-only quick audit completed in about 19 seconds.

Command shape:

```powershell
python -m autobot.v2.cli standard-audit `
  --run-id vps_2026_06_05_grid_quick_snapshot_audit `
  --state-db data/vps_autobot_state_2026-06-04_2026-06-04_121159.db `
  --strategies grid `
  --timeframe 5m `
  --skip-standard-reports `
  --include-regime-context
```

Key output:

```json
{
  "matrix_cells": 14,
  "matrix_success": 14,
  "standard_reports_enabled": false,
  "paper_loader_trades": 455,
  "paper_daily_net_pnl": -0.24345413862193863,
  "paper_vs_research_alignment_counts": {
    "aligned_negative": 8,
    "no_evidence": 5,
    "paper_has_trades_research_missing": 5,
    "paper_missing_research_has_trades": 5,
    "paper_positive_research_negative": 1
  },
  "safety_has_no_live": true
}
```

Snapshot interpretation:

- The grid replay on this dataset had no positive cells.
- Worst replay cells included `XLMZEUR`, `BCHEUR`, `ADAEUR`, `ATOMEUR`, and `AVAXEUR`.
- This is measurement evidence only; it does not change strategy routing or live readiness.

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

Warning: This report used public `/health`; it does not claim a full Docker log audit.

## Recommendation

Use quick mode for broad daily evidence runs. Use full standard reports only for smaller targeted analyses or final validation before any strategy promotion.

