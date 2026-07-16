# AUTOBOT Block 4 — shadow cost-drift safety — 2026-07-16

## Decision

`GO` for fail-closed cost-drift handling in the research/shadow governance
layer.  Cost drift was already recorded in the shadow performance window; it
now has an explicit, non-increasing-risk effect.

## Change

`ShadowSafetyPolicy` now defines monotonic adverse cost-drift thresholds:

| Incremental adverse cost | Automatic outcome |
|---:|---|
| 5 bps | `WATCH` |
| 10 bps | `REDUCE` |
| 20 bps | `DISABLE_NEW_ENTRIES` |
| 40 bps | `QUARANTINE` |

Only positive (adverse) cost drift can trigger these actions.  A favourable
cost difference is recorded but cannot cause an automatic risk increase.
Existing action persistence still prevents later automatic relaxation.

## Boundary

This module is side-effect free and research/shadow-only.  It does not import
the router, signal handler or paper engine, and it cannot create an order,
enable paper capital, enable live, promote a strategy, alter sizing or alter
leverage.

## Evidence

Targeted tests cover every cost threshold, the favourable-cost non-escalation
case, threshold validation, immutable artifacts, runtime-preview rejection and
risk-mandate safety.

## Remaining condition

No strategy has a valid shadow artifact from the new funding/basis research:
the only manifested smoke experiment was stopped as `INSUFFICIENT_DATA`.
Accordingly, this safety policy remains protective infrastructure, not a
trading activation.
