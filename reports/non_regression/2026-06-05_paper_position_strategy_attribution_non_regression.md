# Non-Regression - Paper Position Strategy Attribution - 2026-06-05

Verdict: PASS_WITH_WARNINGS

## Scope

This change improves read-only attribution of official paper trades.

Changed files:

- `src/autobot/v2/paper/ledger_loader.py`
- `tests/paper/test_paper_ledger_loader.py`

When `trade_ledger` rows have no linked `decision_id` or `signal_id`, the loader now reads the optional `positions` table and uses `positions.strategy` as a fallback strategy source.

## What Did Not Change

- No runtime paper execution changed.
- No live execution changed.
- No strategy router behavior changed.
- No risk, sizing, leverage, stop-loss or take-profit changed.
- No dashboard files changed.
- No database schema migration was added.
- No persistent data is written or mutated by the loader.

## Trading Safety

Confirmed:

- `load_state_db_paper_ledger` still opens SQLite via `mode=ro`.
- The change only affects research/reporting attribution.
- No paper or live order can be created.
- No live trading permission is granted.

## Tests

Focused tests:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/paper/test_paper_ledger_loader.py tests/research/test_paper_research_comparison.py -q
```

Result:

```text
12 passed in 0.30s
```

Research/paper regression block:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_v2_cli.py tests/paper tests/research tests/test_pnl_causality_audit.py tests/test_shadow_cost_bridge.py -q
```

Result:

```text
126 passed in 1.56s
```

Syntax validation:

```powershell
python -m compileall -q src
```

Result: PASS.

Note: `compileall` regenerated tracked `.pyc` files; they were restored before commit.

## Real Snapshot Smoke

Command: `standard-audit` on `data/vps_autobot_state_2026-06-04_2026-06-04_121159.db`, scoped to `TRXEUR/grid`.

Before this change, the comparison surfaced `paper_strategy_unknown: 14`.

After this change:

```json
{
  "paper_loader_trade_count": 455,
  "alignment_counts": {
    "no_evidence": 3,
    "paper_has_trades_research_missing": 13,
    "paper_positive_research_negative": 1
  },
  "warning_counts": {
    "paper_research_divergence": 14,
    "paper_sample_below_30_trades": 6,
    "research_sample_below_30_trades": 1
  },
  "safety_has_no_live": true
}
```

Interpretation:

- Historical official paper trades can now be attributed to `dynamic_grid` through `positions.strategy`.
- The former `unknown` strategy gap is resolved for this snapshot.
- Remaining divergences now indicate coverage/runtime-vs-replay gaps, not missing paper strategy attribution.

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

Proceed with broader paper-vs-research coverage: run the standard audit across the full AUTOBOT symbol universe and strategy matrix so the remaining `paper_has_trades_research_missing` buckets can be classified as genuine strategy coverage gaps, timeframe differences, or runtime/replay differences.

