# AUTOBOT Block 3 - Capacity provenance boundary - 2026-07-20

## Verdict

**GO - research/shadow contract hardening only.** Capacity evidence can no
longer validate a shadow simulation from a bare symbol and a liquidity number.

## Delivered behaviour

- `CapacityObservation` now requires an explicit `MarketIdentity`, a source
  snapshot identifier, and ordered `event_time`, `available_time` and
  `ingestion_time` values.
- `TargetPortfolio` now carries the exact source market for each signal-backed
  target weight. A caller-supplied market can only confirm that identity; it
  cannot replace it.
- A target-capacity review rejects missing target identity, exchange/quote
  mismatch, future availability/ingestion or stale market-event evidence with
  `WAITING_FOR_MORE_DATA`.
- Successful reviews record the immutable source snapshot identifiers used for
  their capacity evidence.
- The contract-driven shadow pipeline binds its capacity review to the exact
  `AlphaSignal.market`; it stops before creating an `OrderIntent` when that
  evidence does not match.

## Safety boundary

This change is research/shadow-only. It does not change runtime allocation,
sizing, paper capital, live flags, promotion, leverage, or any order router.
It only adds fail-closed reasons to the isolated contract simulator.

## Validation

- Portfolio construction, contract-shadow and boundary-contract tests:
  `25 passed`.
- Full Python suite: `1797 passed, 6 skipped`.
- Tests cover missing target identity, USD/EUR quote mismatch, stale event
  re-ingested at decision time, future or late-ingested evidence,
  source-snapshot reporting and the absence of an intent/fill on a capacity
  mismatch.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.

## Residual risk / next gate

The runtime allocator remains intentionally separate from the research target
contract. A later Block 3 change must bind observed microstructure profiles to
the same cost-profile fingerprint used by scenario validation; no runtime
allocation may infer either cost or capacity evidence.
