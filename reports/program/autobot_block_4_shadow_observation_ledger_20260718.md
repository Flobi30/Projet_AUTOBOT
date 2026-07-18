# AUTOBOT Block 4 — Research Shadow Observation Ledger — 2026-07-18

## Decision

`GO` for an isolated, append-only shadow-evidence ledger. Block 4 remains
`PARTIAL`: no runtime producer has been wired to this ledger and no strategy is
promoted by it.

## Delivered

- `ShadowObservationLedger` records a shadow decision only for a
  `SHADOW_ELIGIBLE` or `SHADOW` artifact.
- Every write must bind the artifact, source snapshot, complete feature-snapshot
  set, exact `VerifiedFeatureVector` values, vector observation time and an
  aggregate vector fingerprint.
- The SQLite table has append-only triggers and idempotent deterministic IDs.
- The schema hard-blocks paper-capital and live flags at zero.

## Validation

- Hermetic ledger tests prove exact vector binding, duplicate safety,
  append-only behavior, artifact-status rejection and absence of execution
  imports.
- Existing governance, runtime-preview, feature-vector and contract tests are
  included in the focused regression suite.
- Focused regression suite: `49 passed`.
- Research and contract regression suite: `550 passed, 1 skipped`.
- Hermetic unit suite: `1346 passed, 6 skipped`.
- Hermetic integration suite: `316 passed`.

## Safety

- This is a research SQLite ledger, not the official paper ledger.
- It imports no router, executor, paper engine or signal handler.
- It cannot submit, cancel or simulate an order.
- The runtime remains unchanged until a separately reviewed producer can
  provide equivalent point-in-time values.

## Remaining Gate

The next bounded step is a hermetic adapter test: the same canonical inputs
must produce a batch target and a ledgered shadow observation with a
`PARITY_OK` result. Runtime wiring stays blocked until that comparison exists.
