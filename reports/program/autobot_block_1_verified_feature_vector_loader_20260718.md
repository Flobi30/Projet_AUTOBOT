# AUTOBOT Block 1 — Verified Feature Vector Loader — 2026-07-18

## Decision

`GO` for this bounded research-data increment. Block 1 remains `PARTIAL`.

The change closes the batch side of the feature-value provenance boundary. It
does not connect a runtime writer, activate shadow observations, paper capital,
promotion or live trading.

## Delivered

- A batch-only reader can materialize one `VerifiedFeatureVector` from an
  explicit canonical feature snapshot, symbol, timeframe, event time and
  observation time.
- The reader first re-verifies every CSV byte hash, row count, logical
  fingerprint, bundle root, registry fingerprint and feature-version set.
- It only accepts a `READY` bundle with proven point-in-time parity and zero
  unknown ingestion timestamps.
- The vector carries the exact feature values, explicit market identity and
  availability timestamps. Values not ready at the requested observation time,
  missing values, duplicate feature IDs and mismatched versions fail closed in
  the existing contract.
- The historical v2 manifest format did not serialize `runtime_parity_proven`.
  The reader derives it only from the persisted `parity_ok=true` and
  `ingestion_time_unknown_count=0` evidence; a status string alone is never
  sufficient.

## Validation

- Focused canonical-snapshot, vector, preview and contract tests: `29 passed`.
- The new test creates a real `READY` canonical bundle with known ingestion
  times, loads an exact vector, then modifies its CSV and proves that loading
  fails on the material hash check.
- Python compilation passed for the modified batch reader.
- Research and contract regression suite: `547 passed, 1 skipped`.
- Hermetic unit suite: `1346 passed, 6 skipped`.
- Hermetic integration suite: `313 passed`.

## Safety

- No runtime, scheduler, router, paper engine, execution client or private
  Kraken API import was added.
- No market, symbol, quote currency, event time or observation time is inferred.
- This reader cannot submit an order and is not wired to any execution path.

## Remaining Gate

An official shadow observation writer must still consume this exact vector and
be independently compared with the corresponding point-in-time batch decision.
Until then, runtime previews remain fail-closed if their metadata lacks a valid
vector, and Block 1/Block 4 are correctly `PARTIAL`.
