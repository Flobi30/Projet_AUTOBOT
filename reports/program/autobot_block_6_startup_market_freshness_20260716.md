# AUTOBOT Block 6 — Startup market-data freshness — 2026-07-16

## Decision

GO for a bounded runtime-observability correction.  No strategy, order,
capital, paper, live or promotion path was changed.

## Finding

The independent runtime-resilience timer begins two minutes after a container
start and repeats every five minutes.  The decision-learning price sampler was
also scheduled every five minutes, with its first execution delayed by the
full interval.  A healthy restart could therefore report `DATA_STALE` before a
first post-start market observation existed.

## Change

`ColdPathScheduler.schedule_periodic` now accepts an optional bounded
`initial_delay`.  AUTOBOT uses it only for the decision-learning market-sample
refresh:

- first refresh: 30 seconds by default, configurable but never below 5 seconds;
- subsequent refreshes: existing 300-second interval by default;
- collection remains asynchronous on the cold path;
- no order, router, fill, capital or promotion code is imported or called.

The resulting sample is still subject to the existing SQLite write retry and
idempotent sample identifier rules.

## Evidence

- Focused scheduler, decision-learning and resilience tests: 53 passed.
- Full local regression: 1569 passed, 5 skipped.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed before commit.

## Safety invariant

This change improves only freshness evidence.  A missing or stale sample after
the short startup window remains a fail-closed `DATA_STALE` incident.  It does
not relax a risk limit or authorize paper/live execution.

## VPS validation required

After deployment, confirm a decision-learning refresh is recorded before the
next runtime-resilience audit, then verify the audit has fresh data and all
execution flags remain disabled.
