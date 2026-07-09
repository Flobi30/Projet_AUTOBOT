# P16 High Conviction Shadow Paths Non-Regression - 2026-07-09

## Verdict

PASS_WITH_WARNINGS.

The patch only affects research/shadow observation sync path discovery for `high_conviction_swing`. It does not alter live trading, official paper capital, risk, sizing, leverage, UI, or strategy promotion.

## Files Modified

- `src/autobot/v2/paper/shadow_observation_sync.py`
- `tests/paper/test_shadow_observation_sync.py`
- `reports/research/p16_high_conviction_reset_2026-07-09.md`
- `reports/non_regression/2026-07-09_p16_high_conviction_shadow_paths_non_regression.md`

## What Changed

- If `high_conviction_data_paths` is provided explicitly, behavior is unchanged.
- If no High Conviction path is provided, sync now checks the latest daily OHLCV directory adjacent to `data/autobot_state.db`.
- If no daily OHLCV directory exists, the old `high_conviction_data_paths_missing` diagnostic remains.
- This makes manual `shadow-paper-observations` behave consistently with the daily research runner.

## What Did Not Change

- No live trading flag.
- No paper capital flag.
- No strategy promotion.
- No order routing.
- No risk manager.
- No sizing/leverage.
- No UI.
- Grid remains blocked.

## Tests

- `python -m compileall -q src` - PASS
- `$env:PYTHONPATH='src'; python -m pytest tests\paper\test_shadow_observation_sync.py -q` - PASS, `25 passed`
- `$env:PYTHONPATH='src'; python -m pytest tests\paper\test_expected_move_diagnostics.py tests\paper\test_opportunity_score_audit.py tests\paper\test_shadow_observation_sync.py -q` - PASS, `32 passed`

## Warnings

- Latest High Conviction portfolio replay remains weak under costs; it is still research-only.
- Trend Momentum and Mean Reversion remain weak shadow sources and should not receive paper capital.

