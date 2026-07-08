# P14 Pre-Trade Feature Propagation Non-Regression - 2026-07-08

## Verdict

PASS

## Scope

P14 propagates existing pre-trade features into shadow-paper ledger metadata for `opportunity_score_v2`.

No live trading, paper capital, strategy promotion, sizing, leverage, grid runtime, or visible UI behavior was changed.

## Files Modified

- `src/autobot/v2/paper/shadow_observation_sync.py`
- `src/autobot/v2/paper/ledger_loader.py`
- `src/autobot/v2/paper/opportunity_score_audit.py`
- `tests/paper/test_shadow_observation_sync.py`

## Safety Confirmation

- `opportunity_score_v2` remains research-only and shadow-only.
- `score_v2_promotable=false`, `score_v2_paper_capital_allowed=false`, and `score_v2_live_allowed=false` remain enforced in metadata.
- No order routing, live flags, paper-capital routing, sizing, leverage, or grid execution path was modified.
- P14 normalizes only fields already available before entry.
- Forbidden post-trade fields remain excluded from score-v2 inputs: exit, realized PnL, gross/net PnL, MFE/MAE, outcome, and future close.

## What Changed

- Shadow sync now normalizes existing pre-trade fields such as:
  - `expected_move_bps`
  - `estimated_net_edge_bps`
  - `estimated_fees_bps`
  - `estimated_spread_cost_bps`
  - `estimated_slippage_bps`
  - `estimated_total_cost_bps`
  - `risk_reward_ratio`
  - trend/breakout/volatility/liquidity/pair/segment metadata when present
- Missing required score-v2 inputs now produce explicit diagnostics:
  - `score_v2_input_status`
  - `score_v2_required_inputs_present`
  - `feature_missing_reason`
  - `score_v2_optional_missing_features`
- Existing score metadata can be enriched idempotently when P14 input diagnostics are missing.
- The paper ledger loader exposes the normalized pre-trade fields for reports and diagnostics.
- Opportunity score audit now reports score-v2 input coverage by field and strategy.

## Tests

Commands run locally:

```powershell
python -m compileall -q src
$env:PYTHONPATH='src'; python -m pytest tests\paper\test_shadow_observation_sync.py tests\paper\test_opportunity_score_audit.py -q
$env:PYTHONPATH='src'; python -m pytest tests\paper\test_shadow_observation_sync.py tests\paper\test_opportunity_score_audit.py tests\paper\test_p6_score_and_confidence.py tests\paper\test_loss_diagnostics.py tests\test_strategy_validation_registry.py tests\test_v2_cli.py tests\research\test_archived_grid_defaults.py -q
```

Results:

- `compileall`: PASS
- Targeted P14 tests: `27 passed`
- Broader governance/paper/CLI/grid non-regression: `99 passed`

## Coverage Baseline

Before P14, post-P13 observations showed `score_v2=0.0` mainly because required inputs were not visible in ledger metadata:

- `expected_move_bps` missing
- `estimated_total_cost_bps` missing

P14 does not invent missing alpha. It only propagates existing pre-trade metadata and reports missing reasons when unavailable.

## Remaining Risks

- If upstream strategies do not emit a real expected move or cost estimate, rows will still remain `insufficient_data`.
- Trend and mean-reversion shadow observations can still be poor quality; P14 improves measurement, not edge.
- High Conviction still needs fresh closed post-P14 observations before its score-v2 behavior can be judged.

## Recommendation

Let the shadow sync collect fresh P14 observations, then run `opportunity-score-audit` again. P15 should focus on upstream generation of real pre-trade expected-move and risk/reward features, not threshold lowering.
