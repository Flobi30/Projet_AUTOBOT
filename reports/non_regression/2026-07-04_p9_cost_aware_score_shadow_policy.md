# P9 Cost-Aware Score + Shadow Segment Policy - 2026-07-04

## Verdict

PASS_WITH_WARNINGS.

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

## VPS Deployment Smoke

Commit deployed:

```text
74a780e73a42648ec229524c8c75a890a454aa85
```

Runtime checks:

```text
container: autobot-v2 Up, healthy
/health: healthy
websocket: connected
instances: 14
container compileall: PASS
critical log scan: no critical/traceback/database-locked/live-order hit in tail
```

Trading safety flags after deployment:

```text
PAPER_TRADING=true
LIVE_TRADING_CONFIRMATION=false
STRATEGY_ROUTER_LIVE_ENABLED=false
COLONY_AUTO_LIVE_PROMOTION=false
ENABLE_INSTANCE_SPLIT_EXECUTOR unset
```

## VPS P9 Command

```text
python -m autobot.v2.cli score-filter-simulation \
  --state-db data/autobot_state.db \
  --run-id p9_vps_cost_aware \
  --output-dir reports/paper/score_filter_simulation
```

Generated:

```text
reports/paper/score_filter_simulation/p9_vps_cost_aware.json
reports/paper/score_filter_simulation/p9_vps_cost_aware.md
```

## Current Score Baseline

Bucket counts:

```text
high: 137
medium: 1714
low: 196
missing: 2137
```

Baseline scenarios:

| Scenario | Trades | Gross PF | Net PF | Net PnL | Expectancy | Confidence | Promotable |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| all_scored | 2047 | 0.9657 | 0.5390 | -235.64 | -0.1151 | rejected | false |
| high_only | 137 | 1.5191 | 0.7637 | -9.02 | -0.0658 | rejected | false |
| high_plus_medium | 1851 | 0.9139 | 0.5154 | -230.34 | -0.1244 | rejected | false |
| missing_separate | 2137 | 0.7059 | 0.4220 | -376.88 | -0.1764 | rejected | false |
| low_separate | 196 | 1.7220 | 0.8521 | -5.29 | -0.0270 | rejected | false |

Conclusion: the current high bucket improves gross PF, but remains net-losing
after fees/slippage.

## Cost-Aware Score Simulation

| Scenario | Selected | Gross PF | Net PF | Net PnL | Expectancy | Fees | Slippage | Confidence | Promotable |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| current_score_high | 137 | 1.5191 | 0.7637 | -9.02 | -0.0658 | 18.32 | 4.12 | rejected | false |
| fee_adjusted_high | 68 | 2.1439 | 1.2424 | +4.03 | +0.0592 | 8.54 | 1.92 | early_signal | false |
| slippage_adjusted_high | 104 | 1.6344 | 0.8589 | -4.51 | -0.0434 | 15.05 | 3.39 | rejected | false |
| total_cost_adjusted_high | 61 | 2.2526 | 1.3325 | +5.15 | +0.0844 | 8.10 | 1.82 | early_signal | false |
| symbol_adjusted_high | 11 | 0.0100 | 0.0000 | -5.70 | -0.5183 | 0.80 | 0.18 | insufficient_data | false |
| frequency_adjusted_high | 137 | 1.5191 | 0.7637 | -9.02 | -0.0658 | 18.32 | 4.12 | rejected | false |
| expected_net_edge_adjusted_high | 42 | 6.3045 | 4.1830 | +15.74 | +0.3747 | 5.88 | 1.32 | insufficient_data | false |

Interpretation:

- Penalizing high scores by fees or total observed costs materially improves the
  selection in this sample.
- The improved variants remain research-only because sample size is too small
  or confidence is only `early_signal`.
- The `expected_net_edge_adjusted_high` result is a research-only realized
  net-edge proxy, not a deployable forward-looking rule.
- Frequency adjustment did not change selection on this run, so frequency is
  not the main explanation for the high-bucket loss.

## Shadow Segment Policy

Policy counts:

```text
block_shadow_future: 51
watch: 13
insufficient_data: 37
observe: 7
```

Top destructive `block_shadow_future` examples:

| Segment | Trades | Gross PF | Net PF | Net PnL | Reasons |
| --- | ---: | ---: | ---: | ---: | --- |
| missing/trend_momentum/ADAEUR | 90 | 0.0928 | 0.0256 | -33.82 | missing score, negative net, very weak PF |
| missing/trend_momentum/AAVEEUR | 89 | 0.1901 | 0.0996 | -31.62 | missing score, negative net, very weak PF |
| missing/trend_momentum/DOTEUR | 137 | 0.5512 | 0.3099 | -31.30 | missing score, negative net, costs exceed gross |
| missing/trend_momentum/AVAXEUR | 85 | 0.1308 | 0.0520 | -31.21 | missing score, negative net, very weak PF |
| medium/trend_momentum/AVAXEUR | 120 | 0.2682 | 0.1180 | -30.57 | negative net, very weak PF |

Watch-only examples:

| Segment | Trades | Gross PF | Net PF | Net PnL | Reasons |
| --- | ---: | ---: | ---: | ---: | --- |
| high/trend_momentum/BCHEUR | 32 | 1.9485 | 0.9428 | -0.29 | gross positive, net negative after costs |
| high/mean_reversion/LINKEUR | 10 | 6.5442 | 3.3311 | +0.64 | observation only |
| medium/mean_reversion/AAVEEUR | 36 | 3.4722 | 2.3156 | +3.51 | observation only |
| missing/trend_momentum/XXLMZEUR | 168 | 1.3273 | 1.0408 | +3.59 | missing score, non-promotable |

All segment policies are research/shadow-only:

```text
paper_capital_allowed=false
live_allowed=false
promotable=false
```

## Ledger Warnings / Exclusions

```text
opening_leg_missing: 5
realized_pnl_missing: 100
slippage_bps_anomaly: 21
legacy_unattributed: 0
policy_blocked: 455
quality_warning: 0
```

## Final Recommendation

- Do not promote anything.
- Keep `low` and `missing` separated and non-promotable.
- Treat `fee_adjusted_high` and `total_cost_adjusted_high` as promising
  research-only filters to continue observing.
- Keep `expected_net_edge_adjusted_high` as diagnostic only because it uses a
  realized net-edge proxy and cannot be treated as a forward rule yet.
- For P10, add a forward-safe net-edge estimator using only pre-trade metadata
  available before entry: expected move, fee profile, spread/depth, slippage
  estimate, pair health, and recent segment quality. Then replay it without
  using realized PnL in the score.
