# AUTOBOT Block 3 - Capacity evidence fingerprint - 2026-07-20

## Verdict

**GO - research/shadow provenance hardening only.** Capacity evidence now has
an immutable SHA-256 identity rather than relying only on a source label.

## Delivered behaviour

- Every `CapacityObservation` requires the SHA-256 fingerprint of its source
  snapshot.
- The observation exposes a deterministic evidence fingerprint over explicit
  market identity, source snapshot and fingerprint, point-in-time fields,
  executable depth and diagnostic volume.
- `PortfolioCapacityReview` records every accepted capacity-evidence
  fingerprint beside its source snapshot identifiers.
- An invalid or malformed digest fails during construction; an observation
  with changed depth produces different evidence identity.

## Safety boundary

This is a contract-only research/shadow change. It neither resolves a mutable
runtime file nor grants any execution permission. It cannot enable paper
capital, live trading, promotion, leverage, sizing or an order path.

## Validation

- Portfolio construction, contract-shadow, execution-simulator and cost-model
  tests: `35 passed`.
- Full Python suite: `1798 passed, 6 skipped`.
- Tests prove deterministic evidence identity, sensitivity to changed depth,
  invalid fingerprint rejection and preservation of the fingerprint in a
  successful capacity review.
- `python -m compileall -q src`: passed.
- `git diff --check`: passed.

## Residual risk / next gate

The contract carries a source fingerprint but does not yet resolve it against
an immutable canonical-manifest registry. That resolver belongs to a future
data-to-capacity adapter and must remain batch-only until runtime parity is
proven.
