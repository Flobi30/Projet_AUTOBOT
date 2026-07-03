# P7 Score Coverage + Ledger Quality Non-Regression - 2026-07-03

## Verdict

PASS_WITH_WARNINGS.

P7 is a metadata/reporting quality patch. It does not enable live trading,
paper capital, strategy promotion, sizing changes, leverage changes, or UI
changes.

## Files Modified

- `src/autobot/v2/paper/shadow_observation_sync.py`
- `src/autobot/v2/paper/score_filter_simulation.py`
- `src/autobot/v2/paper/paper_confidence.py`
- `src/autobot/v2/paper/loss_diagnostics.py`
- `src/autobot/v2/paper/official_performance.py`
- `src/autobot/v2/paper/ledger_loader.py`
- `src/autobot/v2/paper/ledger_quality.py`
- `tests/paper/test_shadow_observation_sync.py`
- `tests/paper/test_loss_diagnostics.py`
- `tests/paper/test_official_performance.py`
- `tests/paper/test_p6_score_and_confidence.py`

## What Changed

- Existing shadow observations with missing score metadata can now be enriched
  idempotently from prior `decision_ledger` opportunity/router score events.
- The enrichment only uses events whose timestamp is before the trade entry
  and inside the configured match window. Future scores are not used.
- No PnL, fees, slippage, sizing, execution mode, or strategy status is changed.
- `score-filter-simulation` now reports:
  - global bucket counts;
  - coverage by strategy;
  - coverage by symbol;
  - policy exclusions;
  - critical ledger-quality exclusions;
  - loader warning counts.
- Critical ledger warnings now exclude rows from actionable simulations and
  confidence/performance summaries:
  - `opening_leg_missing`;
  - `slippage_bps_anomaly`.
- `realized_pnl_missing` remains excluded by the loader because no closed
  `TradeRecord` is created when realized PnL is absent.

## What Did Not Change

- No live trading enabled.
- No paper capital enabled.
- No strategy promoted.
- No grid reactivation.
- No new strategy added.
- No visible dashboard UI change.
- No sizing, leverage, cost model, or risk rule changed.

## Local Validation

```text
python -m py_compile src/autobot/v2/paper/shadow_observation_sync.py src/autobot/v2/paper/score_filter_simulation.py src/autobot/v2/paper/paper_confidence.py src/autobot/v2/paper/loss_diagnostics.py src/autobot/v2/paper/official_performance.py src/autobot/v2/paper/ledger_quality.py src/autobot/v2/paper/ledger_loader.py
PASS

$env:PYTHONPATH='src'; python -m pytest tests/paper/test_shadow_observation_sync.py tests/paper/test_loss_diagnostics.py tests/paper/test_p6_score_and_confidence.py -q
36 passed

$env:PYTHONPATH='src'; python -m pytest tests/paper/test_loss_diagnostics.py tests/paper/test_official_performance.py tests/paper/test_shadow_observation_sync.py tests/test_v2_cli.py tests/test_persistence_db_reliability.py tests/paper/test_p6_score_and_confidence.py -q
68 passed

python -m compileall -q src
PASS
```

## Baseline Before P7

Last P6 VPS score-filter snapshot:

- Eligible trades: 4,042
- Scored trades: 93
- Score coverage: 2.30%
- Buckets:
  - high: 12
  - medium: 47
  - low: 34
  - missing: 3,949

The root cause is not a missing runtime score: the VPS `decision_ledger`
contains `opportunity_score`. The main gap is historical shadow observations
that were inserted before score metadata propagation and then skipped as
duplicates without enrichment.

## Expected P7 Effect

- Existing duplicate shadow observations can be enriched on the next
  `shadow-paper-observations` run if a prior score event exists.
- Rows with no real score stay `missing`; no artificial score is created.
- Rows with critical ledger-quality warnings remain visible in counts but are
  excluded from actionable score-filter, confidence, and official performance
  decisions.

## VPS Smoke

- Commit deployed: `bd25f4ebe65271483fe038b85e10c84cd9bb0641`
- Container: `autobot-v2` running and healthy
- `/health`: `healthy`
- WebSocket: `connected`
- Instances: `14`
- Flags checked:
  - `PAPER_TRADING=true`
  - `LIVE_TRADING_CONFIRMATION=false`
  - `STRATEGY_ROUTER_LIVE_ENABLED=false`
  - `COLONY_AUTO_LIVE_PROMOTION=false`
  - `ENABLE_INSTANCE_SPLIT_EXECUTOR` unset
- Container compile:
  - `docker exec -e PYTHONPATH=/app/src autobot-v2 python -m compileall -q /app/src`
  - PASS
- Log scan:
  - no critical, traceback, database locked/busy, live-order, or Kraken-order lines in the sampled logs

## P7 Runtime Results

Commands run on VPS:

```text
python -m autobot.v2.cli shadow-paper-observations --state-db data/autobot_state.db --registry-path docs/research/strategy_hypotheses.json --trend-shadow-db data/trend_shadow_lab.db --mean-reversion-shadow-db data/mean_reversion_shadow_lab.db --run-id p7_vps_shadow_sync --output-dir reports/paper/shadow_observations
python -m autobot.v2.cli score-filter-simulation --state-db data/autobot_state.db --run-id p7_vps_score_filter --output-dir reports/paper/score_filter_simulation
python -m autobot.v2.cli paper-loss-diagnostics --state-db data/autobot_state.db --run-id p7_vps_loss --output-dir reports/paper/loss_diagnostics
python -m autobot.v2.cli paper-confidence --state-db data/autobot_state.db --strategy-id trend_momentum --run-id p7_vps_confidence_trend --output-dir reports/paper/confidence --bootstrap-iterations 100
python -m autobot.v2.cli paper-confidence --state-db data/autobot_state.db --strategy-id mean_reversion --run-id p7_vps_confidence_mean_reversion --output-dir reports/paper/confidence --bootstrap-iterations 100
python -m autobot.v2.cli paper-confidence --state-db data/autobot_state.db --strategy-id high_conviction_swing --run-id p7_vps_confidence_high_conviction --output-dir reports/paper/confidence --bootstrap-iterations 100
```

Score coverage before P7:

- Eligible trades: `4,042`
- Scored trades: `93`
- Coverage: `2.30%`
- Buckets: high `12`, medium `47`, low `34`, missing `3,949`

Score coverage after P7 sync:

- Eligible shadow trades: `4,097`
- Scored trades: `1,963`
- Coverage: `47.91%`
- Buckets: high `133`, medium `1,708`, low `122`, missing `2,134`
- Enriched existing duplicate observations:
  - `trend_momentum`: `1,177`
  - `mean_reversion`: `638`
  - `high_conviction_swing`: `0` in this manual sync because no high-conviction data paths were provided; existing high-conviction observations remain visible in the ledger.

Score coverage by strategy:

| Strategy | Total | Scored | Coverage | High | Medium | Low | Missing |
|---|---:|---:|---:|---:|---:|---:|---:|
| high_conviction_swing | 44 | 20 | 45.45% | 7 | 13 | 0 | 24 |
| mean_reversion | 1443 | 656 | 45.46% | 42 | 586 | 28 | 787 |
| trend_momentum | 2610 | 1287 | 49.31% | 84 | 1109 | 94 | 1323 |

Score-filter simulation after quality exclusions:

| Scenario | Trades | Net PF | Net PnL | Expectancy | Max DD | Confidence |
|---|---:|---:|---:|---:|---:|---|
| all_scored | 1963 | 0.4892 | -248.27 | -0.1265 | 25.83% | rejected |
| high_only | 133 | 0.6247 | -12.76 | -0.0959 | 2.51% | rejected |
| high_plus_medium | 1841 | 0.4993 | -231.59 | -0.1258 | 25.21% | rejected |
| missing_separate | 2134 | 0.4168 | -377.77 | -0.1770 | 38.46% | rejected |
| low_separate | 122 | 0.2915 | -16.68 | -0.1368 | 1.76% | rejected |

Interpretation:

- The `high` bucket is better than `medium`, `low`, and `missing`, but still negative net after fees/slippage.
- `missing` remains materially worse and must stay separated from `low`.
- No bucket or strategy is promotable.
- `opportunity_score` is useful as a research filter candidate, not as a promotion gate.

Ledger warnings after P7:

- `realized_pnl_missing`: `100`
- `opening_leg_missing`: `5`
- `slippage_bps_anomaly`: `21`
- Quality-excluded closed observations in current actionable simulations: `0`
- These warnings remain visible in reports. Rows that cannot become valid `TradeRecord` objects are excluded by the loader; critical warning rows are excluded from decision-oriented metrics.

Strategy confidence after P7:

| Strategy | Trades | Net PF | Net PnL | Expectancy | Confidence | Promotable |
|---|---:|---:|---:|---:|---|---|
| trend_momentum | 2610 | 0.3991 | -501.17 | -0.1920 | rejected | false |
| mean_reversion | 1443 | 0.5314 | -109.08 | -0.0756 | rejected | false |
| high_conviction_swing | 44 | 0.7644 | -15.80 | -0.3591 | insufficient_data | false |

## Remaining Risks

- Score coverage can only improve where a real prior score exists in
  `decision_ledger` or the shadow source row itself.
- Historical rows with no matching score remain `missing` by design.
- Quality exclusions may reduce apparent sample size, but this is safer than
  allowing incomplete ledger rows into decisions.
- The high bucket is not profitable net yet, even after improved attribution.
  It should remain observation-only.

## Recommendation P8

After P7 runs on the VPS, inspect:

- score coverage by strategy and symbol;
- score bucket performance after quality exclusions;
- warning counts by type;
- whether future shadow rows are born with score metadata instead of needing
  duplicate enrichment.

Recommended P8:

- Continue accumulating observations with the improved score coverage.
- Move score stamping further upstream for future shadow rows if coverage stops
  improving.
- Investigate why costs erase the `high` bucket's positive gross edge.
- Keep `low` and `missing` non-promotable and separated.
