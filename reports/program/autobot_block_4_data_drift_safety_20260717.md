# AUTOBOT Block 4 — shadow data-drift safety — 2026-07-17

## Decision

`GO` for an additional research/shadow-only guard.  It strengthens observation
quality without enabling shadow execution, paper capital, promotion or live
trading.

## Change

- Added a deterministic `DataDriftAssessment` based on total-variation
  distance between two explicit, point-in-time category distributions.
- Empty, invalid or zero-mass distributions fail closed; missing data is not
  silently interpreted as stable data.
- `ShadowPerformanceWindow` can now carry `data_drift_score` alongside data
  freshness, feature drift, cost drift, rolling PF, expectancy and drawdown.
- `ShadowSafetyPolicy` has monotonic data-drift outcomes: `WATCH`, `REDUCE`,
  `DISABLE_NEW_ENTRIES`, then `QUARANTINE`.
- As with all automatic shadow decisions, a favourable observation cannot
  increase risk, enable a strategy, authorize paper capital or enable live.

## Evidence

The focused governance, preview, mandate, contract and bridge suite passes
with `48 passed`.  Tests cover the deterministic drift score, all four policy
thresholds, malformed baseline data and the absence of any risk increase.

## Limits

This is a reusable research primitive.  A future runtime collector must bind
an explicit point-in-time baseline and current distribution before it can pass
the resulting score to governance.  Until then, no strategy receives an
execution privilege from this work.
