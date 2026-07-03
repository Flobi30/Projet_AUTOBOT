# P7 Score Coverage + Ledger Quality Non-Regression - 2026-07-03

## Verdict

PASS_WITH_WARNINGS before VPS smoke.

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

Pending deployment.

## Remaining Risks

- Score coverage can only improve where a real prior score exists in
  `decision_ledger` or the shadow source row itself.
- Historical rows with no matching score remain `missing` by design.
- Quality exclusions may reduce apparent sample size, but this is safer than
  allowing incomplete ledger rows into decisions.

## Recommendation P8

After P7 runs on the VPS, inspect:

- score coverage by strategy and symbol;
- score bucket performance after quality exclusions;
- warning counts by type;
- whether future shadow rows are born with score metadata instead of needing
  duplicate enrichment.
