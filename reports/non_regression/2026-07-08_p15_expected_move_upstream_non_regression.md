# P15 Expected Move Upstream Non-Regression - 2026-07-08

## Verdict

PASS_WITH_WARNINGS

P15 remains research/shadow-only. No UI, live, paper capital, sizing, leverage, promotion, or grid runtime behavior was enabled.

## What Changed

- `src/autobot/v2/trend_shadow_lab.py`
  - Persist pre-entry `entry_features` on open positions and closed shadow trades.
  - Closed rows now include `entry_features_json`.
- `src/autobot/v2/mean_reversion_shadow_lab.py`
  - Persist pre-entry `entry_features` on open positions and closed shadow trades.
  - Closed rows now include `entry_features_json`.
- `src/autobot/v2/paper/shadow_observation_sync.py`
  - Reads `entry_features_json`.
  - Derives `expected_move_bps` from pre-entry shadow-lab features when explicit router components are absent.
  - Derives `estimated_net_edge_bps = expected_move_bps - estimated_total_cost_bps` when no explicit net edge exists.
  - Preserves precise score-v2 feature provenance.
- `src/autobot/v2/paper/expected_move_diagnostics.py`
  - New read-only P15 diagnostic report for expected move, estimated costs, net edge, destructive segments, and High Conviction data-path status.
- `src/autobot/v2/cli.py`
  - New CLI: `expected-move-diagnostics`.
- Tests added/updated:
  - `tests/test_trend_shadow_lab.py`
  - `tests/test_mean_reversion_shadow_lab.py`
  - `tests/paper/test_shadow_observation_sync.py`
  - `tests/paper/test_expected_move_diagnostics.py`

## What Did Not Change

- No live trading flag changed.
- No paper-capital route enabled.
- No strategy promoted.
- No sizing/risk/leverage changed.
- No dashboard/UI change.
- Grid remains blocked/research-only.
- Historical shadow rows are not rewritten.

## Tests

- `python -m compileall -q src` : PASS
- `$env:PYTHONPATH='src'; python -m pytest tests\test_trend_shadow_lab.py tests\test_mean_reversion_shadow_lab.py tests\paper\test_shadow_observation_sync.py tests\paper\test_expected_move_diagnostics.py tests\paper\test_opportunity_score_audit.py tests\test_v2_cli.py -q` : PASS, 69 passed
- `$env:PYTHONPATH='src'; python -m pytest tests\paper tests\test_strategy_validation_registry.py tests\research\test_archived_grid_defaults.py tests\test_v2_cli.py -q` : PASS, 117 passed

## Trading Safety

- `expected-move-diagnostics` is read-only.
- Score-v2 metadata stays `promotable=false`, `paper_capital_allowed=false`, `live_allowed=false`.
- Expected move derivation uses only pre-entry fields from shadow labs:
  - trend: ATR, momentum, breakout, EMA spread.
  - mean reversion: expected gross/net edge and estimated round-trip cost.
- Forbidden post-trade fields are not used for expected move:
  - no realized/net/gross PnL,
  - no exit price,
  - no MFE/MAE,
  - no future close/outcome.

## P15 Diagnostic Meaning

Historical post-P14 observations may still show `expected_move_bps=0.0` because old closed shadow rows did not persist `entry_features_json`. Future shadow rows closed after this patch should carry the pre-entry features needed by score v2.

High Conviction remains dependent on the daily/research runner providing OHLCV data paths. If paths are missing, the new diagnostic reports `high_conviction_data_paths_missing` instead of forcing synthetic trades.

## Risks Remaining

- Fresh post-P15 observations are required before concluding whether trend/mean reversion genuinely have positive expected move.
- If trend still produces negative estimated net edge after fresh feature persistence, P16 should reduce or block destructive shadow segments.
- If High Conviction still has no data paths in the daily runner, P16 should wire the existing OHLCV paths into shadow sync.

## Next Action

Deploy P15, let fresh shadow trades close, then run:

```powershell
python -m autobot.v2.cli expected-move-diagnostics --state-db data/autobot_state.db
```

Use that report to decide whether to keep, reduce, or block trend/mean reversion shadow segments and whether High Conviction data paths need a runner fix.
