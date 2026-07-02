# P5 Opportunity Score Diagnostic Non-Regression - 2026-07-02

## Verdict

PASS_WITH_WARNINGS

The P5 patch only hardens shadow observation sync and documents the P5 diagnostic. It does not change live trading, official paper-capital routing, sizing, leverage, strategy parameters, dashboard UI, or strategy promotion.

Warnings:

- `opportunity_score` has only 65 scored trades out of 4010; conclusions are early-signal only.
- Runtime logs showed recent `database is locked` errors outside this sync path; P6 should harden runtime persistence retries.

## Files Modified

- `src/autobot/v2/paper/shadow_observation_sync.py`
- `tests/paper/test_shadow_observation_sync.py`
- `reports/research/p5_opportunity_score_diagnostic_2026-07-02.md`
- `reports/non_regression/2026-07-02_p5_opportunity_score_diagnostic.md`

## What Changed

Shadow sync hardening:

- Added SQLite connection timeout and busy timeout for sync.
- Added commits after each source to avoid holding write transactions during High Conviction replay.
- Made High Conviction source ids stable across replay `run_id` changes.
- Added economic duplicate detection for High Conviction closing trades.
- Added unique `trade_ledger.trade_id` index for sync-created ledgers.
- Fixed High Conviction negative cost validation.

Tests added:

- Sync commits before High Conviction replay can write/read the DB.
- High Conviction sync remains idempotent if replay run_id changes.
- High Conviction negative costs are rejected.

## What Did Not Change

- No live flag changed.
- No paper-capital flag changed.
- No Kraken order path changed.
- No strategy was promoted.
- No grid path was re-enabled.
- No dashboard UI changed.
- No sizing/leverage/risk rule changed.
- No strategy parameters were optimized.

## Tests

Command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests\paper\test_shadow_observation_sync.py tests\paper\test_loss_diagnostics.py tests\research\test_daily_data_collection_runner.py tests\test_v2_cli.py -q
```

Result:

- 59 passed.

Command:

```powershell
python -m compileall -q src
```

Result:

- Passed.

Note: a first pytest run without `PYTHONPATH=src` failed at import collection with `ModuleNotFoundError: No module named 'autobot'`; rerun with the standard AUTOBOT environment passed.

## Trading Safety

Confirmed by code scope and tests:

- `trend_momentum`, `mean_reversion`, and `high_conviction_swing` remain shadow-only.
- `opportunity_scoring` remains metadata/filter only, not an alpha strategy.
- `dynamic_grid` / grid remains blocked.
- Shadow observations do not permit paper-capital or live promotion.
- No live order can be created by this patch.

## P5 Diagnostic Summary

Bucket results:

- `high`: 8 trades, net PF 1.16, net PnL +0.91.
- `medium`: 40 trades, net PF 0.78, net PnL -3.31.
- `low`: 17 trades, net PF 0.00, net PnL -6.38.
- `missing`: 3945 trades, net PF 0.42, net PnL -623.35.

Conclusion:

- `opportunity_score` shows a plausible early hierarchy but is not statistically usable yet.
- `high_conviction_swing` produces observations but remains insufficient and net-negative.
- P6 should focus on DB retry hardening and longer score coverage, not promotion.

## Runtime/VPS Expectations

After deploy, verify:

- GitHub/VPS/container on the same commit.
- `/health` healthy.
- WebSocket connected.
- PAPER_TRADING remains true.
- Live confirmation remains false.
- No live orders.
- No strategy promotion.
- No grid reactivation.

## Recommendation

Proceed to P6 only as research-only:

- strengthen runtime DB write retries;
- analyze from DB snapshots;
- keep `opportunity_score` as a shadow-only filter candidate;
- wait for materially larger scored sample before any capital decision.
