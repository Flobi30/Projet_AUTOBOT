# P9 Cost-Aware Score + Shadow Segment Policy - 2026-07-04

## Verdict

PASS_WITH_WARNINGS before VPS smoke.

P9 is a research-only observability/reporting patch. It does not enable live
trading, paper capital, strategy promotion, sizing changes, leverage changes,
or visible UI changes.

## Commit Verification

- Local HEAD before P9 code changes included final P8 report commit:
  `1bd512cd5f73a20392394948d2193d33d71b263b`.
- Local history contains P8 code commit:
  `1e217d3bcfdf79abc2cf733462788293b7484718`.
- VPS pre-check also confirmed `1e217d3` is an ancestor of deployed `HEAD`.

## Files Modified

- `src/autobot/v2/paper/score_filter_simulation.py`
- `tests/paper/test_p6_score_and_confidence.py`

## What Changed

- `score-filter-simulation` now includes cost-aware score scenarios:
  - `current_score_high`
  - `fee_adjusted_high`
  - `slippage_adjusted_high`
  - `total_cost_adjusted_high`
  - `symbol_adjusted_high`
  - `frequency_adjusted_high`
  - `expected_net_edge_adjusted_high`
- Cost-aware scenarios only penalize existing real scores; they never invent a
  score for missing rows.
- `score-filter-simulation` now produces a research-only shadow segment policy:
  - `observe`
  - `watch`
  - `block_shadow_future`
  - `insufficient_data`
- Every cost-aware scenario and every segment policy remains
  `promotable=false`, `paper_capital_allowed=false`, `live_allowed=false`.

## What Did Not Change

- No live trading enabled.
- No paper capital enabled.
- No strategy promoted.
- No grid reactivation.
- No new strategy added.
- No visible dashboard UI change.
- No sizing, leverage, cost model, risk rule, or router rule changed.
- No historical ledger rewrite.

## Local Validation

```text
$env:PYTHONPATH='src'; python -m pytest tests\paper\test_p6_score_and_confidence.py tests\paper\test_loss_diagnostics.py -q
18 passed

$env:PYTHONPATH='src'; python -m pytest tests\paper tests\test_v2_cli.py tests\test_strategy_validation_registry.py -q
96 passed

python -m compileall -q src
PASS

python -m py_compile src\autobot\v2\paper\score_filter_simulation.py
PASS
```

## Pending VPS Smoke

Run after deployment:

```text
python -m autobot.v2.cli score-filter-simulation --state-db data/autobot_state.db --run-id p9_vps_cost_aware --output-dir reports/paper/score_filter_simulation
```

Then verify:

- GitHub/VPS/container sync.
- `/health`.
- WebSocket connected.
- live/paper flags unchanged.
- cost-aware scenarios remain non-promotable.
- shadow segment policy does not alter runtime routing.

## Recommendation Placeholder

Pending VPS data. Expected output categories:

- segments to `block_shadow_future`;
- segments to keep `watch`;
- cost-aware high-only comparison;
- P10 recommendation without promotion.
