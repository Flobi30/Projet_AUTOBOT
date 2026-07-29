# AUTOBOT Block 4 — Read-only Shadow Ledger Health Evidence

## Scope

This local-only change makes `strategy-autonomy-check --state-db` use the
official attributed ledger instead of silently evaluating an empty health
snapshot. It does not alter the runtime, routes, paper engine, sizing,
leverage, promotion policy, or any safety flag.

## Evidence Boundary

- Source: the existing official post-P0 performance report, whose SQLite loader
  opens the state database in read-only mode.
- Eligible observations: attributed, reportable `shadow_paper` closing trades
  only.
- Excluded: legacy/unattributed records, retired strategies, critical ledger
  quality failures, and every `paper_capital` metric.
- Health metrics are applied only after the configurable minimum number of
  closed shadow trades (default: `30`) and only when fee and slippage evidence
  are complete and PF/expectancy are finite.
- A negative qualified health metric can only drive the existing kill/reduce
  classifiers. It cannot enable paper capital, live, promotion, sizing, or an
  order path.

## Local Smoke Result

`trend_momentum` was checked against the local `data/autobot_state.db`:

- attributed shadow closing trades: `0`;
- result: `insufficient_closed_trades_for_health:0/30`;
- final mandate decision: `BLOCK`;
- `paper_capital_allowed=false`, `live_allowed=false`, `promotable=false`.

The check is expected to remain non-authorizing until clean shadow evidence
exists. It did not write to the state DB or create an order.

## Tests

Targeted validation after implementation:

```text
python -m py_compile src/autobot/v2/research/strategy_ledger_health_evidence.py src/autobot/v2/cli.py
PYTHONPATH=src python -m pytest \
  tests/research/test_strategy_ledger_health_evidence.py \
  tests/research/test_strategy_risk_mandates.py \
  tests/paper/test_official_performance.py \
  tests/paper/test_p6_score_and_confidence.py \
  tests/test_v2_cli.py -q
```

Result: `84 passed`.

The new focused coverage proves that:

1. the state DB bytes are unchanged after evidence building and CLI use;
2. shadow losses can produce a research-only kill classification;
3. paper-capital rows are reported as ignored, never mixed into shadow health;
4. a small sample remains insufficient rather than becoming a positive health
   signal;
5. the adapter cannot import the execution runtime boundary.

## VPS Status

No VPS access, deployment, container rebuild, or runtime smoke was attempted.
Hetzner maintenance is active, so exact GitHub/VPS/container alignment remains
unverified and deployment is deferred.

## Decision

`GO_LOCAL_ONLY` — the local evidence boundary is tested. `WAITING_FOR_VPS` for
the controlled deployment and runtime proof after maintenance.
