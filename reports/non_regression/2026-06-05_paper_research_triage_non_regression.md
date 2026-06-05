# Non-Regression - Paper/Research Triage - 2026-06-05

Verdict: PASS_WITH_WARNINGS

## Scope

This change strengthens the read-only paper vs research comparison report.

Changed files:

- `src/autobot/v2/research/paper_research_comparison.py`
- `tests/research/test_paper_research_comparison.py`

The report now exposes:

- alignment counts;
- diagnostic counts;
- recommendation counts;
- warning counts;
- priority buckets sorted by divergence size;
- explicit `paper_strategy_attribution_missing` diagnostics when official paper trades cannot be tied back to a strategy.

## What Did Not Change

- No dashboard files changed.
- No paper runtime execution changed.
- No Kraken live execution path changed.
- No risk manager, sizing, leverage, stop-loss or take-profit changed.
- No strategy router runtime behavior changed.
- No Docker/VPS configuration changed.
- No persistent DB or strategy registry mutation was added.

## Trading Safety

Confirmed:

- This is report-only research code.
- No paper or live order can be created by this module.
- No live trading permission is granted.
- The standard audit smoke retained the safety note `No live trading permission is granted.`

## Tests

Targeted tests:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/research/test_paper_research_comparison.py tests/test_v2_cli.py::test_cli_standard_audit_runs_full_read_only_bundle -q
```

Result:

```text
7 passed in 0.27s
```

Research/paper regression block:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_v2_cli.py tests/paper tests/research tests/test_pnl_causality_audit.py tests/test_shadow_cost_bridge.py -q
```

Result:

```text
125 passed in 1.57s
```

Syntax validation:

```powershell
python -m compileall -q src
```

Result: PASS.

Note: `compileall` regenerated tracked `.pyc` files; they were restored before commit.

## Real Snapshot Smoke

Command: `standard-audit` on `data/vps_autobot_state_2026-06-04_2026-06-04_121159.db`, scoped to `TRXEUR/grid`.

Key paper/research triage output:

```json
{
  "alignment_counts": {
    "no_evidence": 1,
    "paper_has_trades_research_missing": 14,
    "paper_missing_research_has_trades": 1
  },
  "top_warnings": {
    "paper_research_divergence": 15,
    "paper_sample_below_30_trades": 6,
    "paper_strategy_unknown": 14,
    "research_sample_below_30_trades": 1
  },
  "safety_has_no_live": true
}
```

Interpretation:

- The comparison is now more actionable.
- A major current evidence gap is not simply a bad strategy result; many official paper trades are recorded with `strategy_id=unknown`.
- Fixing strategy attribution in the paper ledger/runtime trace should happen before trusting strategy-level paper vs research conclusions.

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

Proceed to the next validation step: fix or audit paper strategy attribution so official paper trades can be mapped to the strategy/motor that created them. Do not tune strategies based on paper-vs-research by strategy until `paper_strategy_unknown` is resolved or explained.

