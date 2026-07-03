# P8 High Bucket + Score Stamping Non-Regression - 2026-07-03

## Verdict

PASS_WITH_WARNINGS.

P8 is a read-only observability/reporting patch. It does not enable live
trading, paper capital, strategy promotion, sizing changes, leverage changes,
or visible UI changes.

## Files Modified

- `src/autobot/v2/paper/shadow_observation_sync.py`
- `src/autobot/v2/paper/loss_diagnostics.py`
- `src/autobot/v2/paper/ledger_loader.py`
- `tests/paper/test_shadow_observation_sync.py`
- `tests/paper/test_loss_diagnostics.py`

## What Changed

- Shadow observation sync now reports whether newly inserted observations were
  born with score metadata, separately from historical duplicate enrichment.
- Score metadata now carries an explicit origin:
  - `source`
  - `decision_ledger_lookup`
  - `missing`
- The ledger loader exposes `opportunity_metadata_origin`.
- `paper-loss-diagnostics` now includes a High Bucket Autopsy:
  - high bucket by strategy/symbol/timeframe/regime;
  - gross PF vs net PF;
  - average cost per trade;
  - gross-to-net expectancy delta;
  - fee/slippage shares of cost;
  - research-only segment rules.

## What Did Not Change

- No live trading enabled.
- No paper capital enabled.
- No strategy promoted.
- No grid reactivation.
- No new strategy added.
- No visible dashboard UI change.
- No sizing, leverage, cost model, risk rule, or router rule changed.

## Local Validation

```text
$env:PYTHONPATH='src'; python -m pytest tests/paper/test_shadow_observation_sync.py tests/paper/test_loss_diagnostics.py -q
28 passed

$env:PYTHONPATH='src'; python -m pytest tests/paper/test_shadow_observation_sync.py tests/paper/test_loss_diagnostics.py tests/paper/test_p6_score_and_confidence.py tests/paper/test_official_performance.py tests/test_v2_cli.py tests/test_persistence_db_reliability.py -q
68 passed

python -m compileall -q src
PASS
```

## Expected VPS Validation

Run after deployment:

```text
python -m autobot.v2.cli shadow-paper-observations --state-db data/autobot_state.db --registry-path docs/research/strategy_hypotheses.json --trend-shadow-db data/trend_shadow_lab.db --mean-reversion-shadow-db data/mean_reversion_shadow_lab.db --run-id p8_vps_shadow_sync --output-dir reports/paper/shadow_observations
python -m autobot.v2.cli paper-loss-diagnostics --state-db data/autobot_state.db --run-id p8_vps_loss --output-dir reports/paper/loss_diagnostics
python -m autobot.v2.cli score-filter-simulation --state-db data/autobot_state.db --run-id p8_vps_score_filter --output-dir reports/paper/score_filter_simulation
```

## VPS Deployment Smoke

Commit deployed:

```text
1e217d3bcfdf79abc2cf733462788293b7484718
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

## P8 Shadow Score Stamping

Global score coverage after the VPS sync:

```text
total shadow trades: 4098
scored: 1964
score coverage: 47.93%
high: 133
medium: 1708
low: 123
missing: 2134
```

New observations created during the P8 sync:

```text
trend_momentum inserted: 1
trend_momentum inserted score coverage: 100.00%
trend_momentum inserted score origin: source=1
mean_reversion inserted: 0
high_conviction_swing inserted: 0, warning=high_conviction_data_paths_missing
opportunity_scoring inserted: 0, warning=scoring_layer_no_direct_trade_source
```

Conclusion: new writes can now be born with score metadata when the source
already carries a real score. No artificial score is created. Historical rows
remain enriched separately or `missing`.

## High Bucket Autopsy

The high bucket is better than the lower buckets in gross terms, but still
loses net after costs:

```text
bucket: high
trades: 133
gross PF: 1.2493
net PF: 0.6247
gross PnL: +5.89 EUR
net PnL: -12.76 EUR
net expectancy: -0.0959 EUR/trade
average cost: 0.1402 EUR/trade
gross-to-net expectancy delta: 0.1402 EUR/trade
win rate net: 36.84%
max drawdown: 25.11 EUR
dominant loss source: fees_erode_edge
recommendation: cost_review_required
```

High bucket by strategy:

| Strategy | Trades | Gross PF | Net PF | Net PnL | Avg Cost | Recommendation |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| high_conviction_swing | 7 | 3.2644 | 1.4440 | +3.22 | 0.9508 | continue_observation |
| mean_reversion | 42 | 0.6571 | 0.3238 | -4.51 | 0.0625 | disabled_segment_recommended |
| trend_momentum | 84 | 0.8475 | 0.4292 | -11.46 | 0.1115 | disabled_segment_recommended |

High bucket by symbol:

| Symbol | Trades | Gross PF | Net PF | Net PnL | Dominant Source | Recommendation |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| BCHEUR | 42 | 2.4501 | 1.1733 | +2.18 | not_loss_segment | continue_observation |
| TRXEUR | 38 | 1.0106 | 0.3435 | -3.35 | fees_erode_edge | cost_review_required |
| XXLMZEUR | 11 | 0.0100 | 0.0000 | -5.70 | signal_brut_negative | disabled_segment_recommended |
| LINKEUR | 42 | 0.8803 | 0.4439 | -5.89 | signal_brut_negative | disabled_segment_recommended |

Gross-positive but net-negative high segments:

| Segment | Trades | Gross PF | Net PF | Net PnL | Avg Cost | Recommendation |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| trend_momentum/BCHEUR/trend | 32 | 1.9485 | 0.9428 | -0.29 | 0.1079 | cost_review_required |
| mean_reversion/TRXEUR/range | 22 | 1.0035 | 0.3241 | -1.41 | 0.0645 | cost_review_required |
| trend_momentum/TRXEUR/trend | 16 | 1.0169 | 0.3570 | -1.94 | 0.1230 | cost_review_required |

Research-only segment rules produced by the report:

```text
continue_observation: 7
block_shadow_candidate: 3
insufficient_data: 0
paper_capital_allowed: false
live_allowed: false
low_missing_policy: low and missing stay separated and non-promotable
```

## Score Filter Simulation

All score-filter scenarios remain rejected and non-promotable:

| Scenario | Trades | Gross PF | Net PF | Net PnL | Confidence | Promotable |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| all_scored | 1964 | 0.8733 | 0.4889 | -248.62 | rejected | false |
| high_only | 133 | 1.2493 | 0.6247 | -12.76 | rejected | false |
| high_plus_medium | 1841 | 0.8824 | 0.4993 | -231.59 | rejected | false |
| exclude_missing | 1964 | 0.8733 | 0.4889 | -248.62 | rejected | false |
| missing_separate | 2134 | 0.6968 | 0.4168 | -377.77 | rejected | false |
| low_separate | 123 | 0.6880 | 0.2873 | -17.03 | rejected | false |

## Ledger Warnings

The diagnostics still report historical quality warnings:

```text
realized_pnl_missing: 100
opening_leg_missing: 5
slippage_bps_anomaly: 21
```

These are not used to promote any strategy. They remain follow-up cleanup /
exclusion candidates, not evidence for paper capital.

## Recommendation

- Continue collection with P8 score-origin tracking enabled.
- Keep `low` and `missing` separated and non-promotable.
- Do not promote `high_only`: high has positive gross PF but loses after costs.
- Keep watching `high_conviction_swing` and `BCHEUR`, but sample size is tiny
  and not candidate-grade.
- For P9, either:
  - improve score calibration so high requires a post-cost edge, or
  - add research-only shadow segment exclusion for clearly destructive
    `trend_momentum`/`mean_reversion` high-bucket segments.
