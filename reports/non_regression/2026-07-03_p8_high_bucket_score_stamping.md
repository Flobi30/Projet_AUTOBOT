# P8 High Bucket + Score Stamping Non-Regression - 2026-07-03

## Verdict

PASS_WITH_WARNINGS before VPS smoke.

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

## Pending VPS Smoke

- GitHub/VPS/container sync.
- `/health`.
- WebSocket.
- live/paper flags.
- high bucket autopsy numbers from the VPS ledger.
- confirmation that no promotion/paper capital/live was enabled.

## Recommendation Placeholder

Pending VPS data. Expected decision categories:

- continue collecte;
- cut/review weak shadow segments only as research policy;
- retravailler score if high remains cost-eroded;
- keep low/missing separated and non-promotable.
