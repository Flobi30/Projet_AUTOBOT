# AUTOBOT Block 1 — Research Verified Feature-Vector Publication

## Decision

`GO` for the bounded data-publication gate. Block 1 remains `PARTIAL`.

## Scope

The daily public-data collection job now publishes a compact, atomic and
idempotent research-only JSON hand-off when its canonical feature snapshot can
prove at least one fully available vector. The output remains under
`data/research/` and is excluded from Git.

## Guarantees

- The publication selects vectors using the feature snapshot's own generated
  UTC timestamp; no caller can silently substitute wall-clock time.
- Every selected vector is from a materially verified READY bundle and every
  feature was available at the observation timestamp.
- Re-running the same daily run accepts identical evidence and rejects a path
  already containing different or tampered evidence.
- The daily report records `ok`, `blocked` or `skipped`; insufficient features
  never become a fabricated vector.
- The publisher imports no router, signal handler or paper engine and cannot
  create a signal, intent, order, fill, promotion, paper-capital allocation or
  live action.

## Tests

- Publication atomicity, idempotence, tamper rejection and import isolation:
  `tests/research/test_verified_feature_vector_publication.py`.
- Daily data-collection report includes the publication outcome:
  `tests/research/test_daily_data_collection_runner.py`.
- Feature timing, bundle integrity and strict vector parsing remain covered by
  `test_canonical_feature_snapshot.py` and `test_verified_feature_vector.py`.

## Remaining Gate

The publication is deliberately not consumed by the runtime. A later,
separately reviewed adapter must independently reproduce the same values and
prove batch/shadow parity before it can feed non-executable shadow previews.
The runtime order path remains unchanged and fail-closed.

## Safety

- Public research data only.
- No secrets, private API, order endpoint, paper capital, live execution or
  automatic promotion.
- Grid remains retired from runtime execution.
