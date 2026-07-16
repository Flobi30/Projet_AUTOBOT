# AUTOBOT Block 3 — research capacity curve — 2026-07-16

## Decision

`GO` for a bounded, research-only capacity-curve primitive.  It fills the
remaining audited gap between a single capacity check and an explicit capital
grid, without changing allocation, sizing, shadow routing, paper capital or
live execution.

## Implementation

`src/autobot/v2/research/portfolio_construction.py` now exposes
`estimate_capacity_curve`.  Given observed liquidity or observed volume and a
strict maximum participation rate, it evaluates an ordered set of proposed
notionals with the existing capacity check.

- Depth has not been inferred when it is absent: the curve returns
  `WAITING_FOR_MORE_DATA`.
- The result is deterministic, spot/research-only and carries explicit false
  flags for paper capital and live.
- It reports the observed source, capacity limit, utilization ratio and a
  reason for each proposed capital level.
- It neither produces an order nor is imported by the order router, paper
  engine or runtime signal handler.

## Evidence

Focused tests cover sorted deterministic levels, observed-liquidity
participation limits, an exceeded level, and the missing-depth fail-closed
case.  The existing execution simulator already independently covers partial
fills, expiry, stale data, market minima, pessimistic costs and restart
determinism.

## Scope and limits

The curve is only as credible as its observed liquidity/volume input.  It is
not an impact model and is not a paper-capital approval.  A future strategy
must still pass net-cost, statistical, concentration, execution-scenario and
human-review gates before any paper mandate can be considered.

## Safety

- No paper capital, live, promotion, sizing or leverage flag changed.
- No UI change.
- Grid remains retired/no-go.
- No runtime order path was changed.
