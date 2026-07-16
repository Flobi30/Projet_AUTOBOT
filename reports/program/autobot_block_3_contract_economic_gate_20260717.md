# AUTOBOT Block 3 — contract economic gate — 2026-07-17

## Decision

`GO` for the bounded research/shadow hardening delivered here.  This is not a
paper-capital or live readiness decision: Block 3 remains `PARTIAL` until the
future OMS, reconciliation and production-parity work is complete.

## What changed

- A shadow candidate now carries the fingerprint of the central cost profile
  used to calculate its net edge.  The contract pipeline rejects a missing or
  changed fingerprint.
- The same candidate is projected against central, pessimistic and stress cost
  scenarios.  A non-positive pessimistic net edge blocks the shadow simulation.
- A risk mandate now has an explicit `shadow_notional_max_eur`.  Its default is
  zero, so a virtual shadow intent fails closed unless its mandate sets a
  bounded virtual notional.  This field cannot authorize paper capital or live
  trading.
- The legacy direct BUY path, the shadow-to-paper bridge, the legacy ensemble
  entry path, and the automatic shadow-promotion loop are retired regardless of
  stale legacy environment flags.
- The 24-layer coverage matrix records the new cost, capacity and simulation
  evidence.

## Safety invariants

- No paper capital, live flag, order-router permission, sizing or leverage was
  enabled or increased.
- The retired paths return explicit research-only reasons before accessing a
  signal handler, positions or a paper executor.
- Protective exits were not changed by the legacy BUY quarantine.
- Grid remains retired/no-go.

## Local evidence

- Focused contracts, simulator, shadow pipeline, legacy-path and handler suite:
  `81 passed`.
- Research suite: `488 passed, 1 skipped`.
- Full repository suite: `1627 passed, 6 skipped, 1 environment deprecation
  warning`.
- `python -m py_compile` on touched modules and `python -m compileall -q src`:
  passed.
- `git diff --check`: passed before commit.

## Residual risks

- The historical paper engine and its legacy OMS remain separate from the
  contract simulator.  They are not evidence for paper readiness.
- The old source code has not become a production contract path merely because
  it is quarantined.  Block 5 must complete the canonical order lifecycle,
  append-only ledger reconstruction and reconciliation before any human paper
  review.
- Cost scenarios are conservative model projections.  They still require later
  calibration from real, non-authorizing shadow observations.

## Next gate

Continue with Block 4: bind every shadow decision to immutable artifacts and
feature snapshots, then verify rolling drift actions can only reduce or block
risk.  Automatic promotion, paper capital and live execution remain out of
scope.
